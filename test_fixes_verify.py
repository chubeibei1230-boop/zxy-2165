import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:8124/api'


def test_all_fixes():
    print("=" * 60)
    print("四个问题修复验证测试")
    print("=" * 60)

    print("\n【准备测试数据】创建新托盘 TRAY-FIX-001")
    tray_data = {
        'tray_code': 'TRAY-FIX-001',
        'capacity': 100,
        'area': '修复测试区',
        'applicable_sessions': '场次A,场次B',
        'responsible_person': '测试员',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    if resp.status_code != 201:
        resp = requests.get(f'{BASE_URL}/trays/?search=TRAY-FIX-001')
        tray = resp.json()['results'][0]
        tray_id = tray['id']
    else:
        tray = resp.json()
        tray_id = tray['id']
    print(f"  托盘ID: {tray_id}")

    print("\n" + "=" * 60)
    print("问题1: 有未处理异常单时，不能直接确认清点记录恢复可用")
    print("=" * 60)

    print("  领取 -> 归还 -> 清点(大差异观察)")
    requests.post(f'{BASE_URL}/trays/pickup/', json={'tray_id': tray_id, 'session': '场次A', 'receiver': '测试人'})
    resp = requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray_id, 'actual_count': 85, 'expected_count': 100,
        'diff_description': '差异15张'
    })
    inventory_id = resp.json()['inventory']['id']
    print(f"  托盘状态: {resp.json()['tray']['status_display']}")
    print(f"  清点记录ID: {inventory_id}")

    print("\n  登记异常处理单")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray_id,
        'inventory_record_id': inventory_id,
        'source': 'inventory_diff',
        'handler': '处理人A',
        'measures': '调查差异',
        'description': '差异15张需要调查'
    })
    abnormal_id = resp.json()['id']
    print(f"  异常单ID: {abnormal_id}, 状态: {resp.json()['status_display']}")

    print("\n  尝试直接确认清点记录 -> 应该被拦截")
    resp = requests.post(f'{BASE_URL}/trays/confirm/', json={
        'inventory_id': inventory_id,
        'confirmer': '管理员',
        'conclusion': '直接确认跳过异常'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 问题1修复: 有未处理异常单时不能直接确认清点")
    else:
        print("  ❌ 问题1未修复: 有未处理异常单仍能确认清点！")

    print("\n" + "=" * 60)
    print("问题2: 异常处理完成(resolve)自动确认清点，托盘直接恢复可用")
    print("=" * 60)

    print("  当前清点记录状态(确认前): 待确认")
    resp = requests.get(f'{BASE_URL}/inventories/{inventory_id}/')
    print(f"  清点确认状态: {resp.json()['confirm_status_display']}")

    print("  开始处理 -> resolve 异常")
    requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/start_processing/')
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/resolve/', json={
        'result': '已查明原因，客户归还补齐',
        'measures': '联系客户追回'
    })
    print(f"  resolve状态码: {resp.status_code}")
    print(f"  异常状态: {resp.json()['abnormal']['status_display']}")
    print(f"  托盘状态: {resp.json()['tray']['status_display']}")

    print("\n  检查关联清点记录是否被自动确认:")
    resp = requests.get(f'{BASE_URL}/inventories/{inventory_id}/')
    inv_status = resp.json()['confirm_status_display']
    inv_confirmer = resp.json()['confirmer']
    inv_conclusion = resp.json()['conclusion']
    print(f"  清点确认状态: {inv_status}")
    print(f"  清点确认人: {inv_confirmer}")
    print(f"  清点确认结论: {inv_conclusion}")

    resp = requests.get(f'{BASE_URL}/trays/{tray_id}/')
    tray_status = resp.json()['status']
    print(f"  托盘状态: {resp.json()['status_display']}")
    if tray_status == 'available':
        print("  ✅ 问题2修复: resolve 后清点自动确认，托盘直接恢复可用")
    else:
        print("  ❌ 问题2未修复: 托盘未恢复可用！")

    print("\n  验证托盘可以再次领取(闭环):")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={'tray_id': tray_id, 'session': '场次B', 'receiver': '测试人2'})
    print(f"  领取状态码: {resp.status_code}")
    if resp.status_code == 200:
        print("  ✅ 托盘可以正常领取，闭环完整")
    else:
        print(f"  ❌ 领取失败: {resp.json()}")

    print("\n" + "=" * 60)
    print("问题3: 创建异常单时校验异常来源是否匹配真实情况")
    print("=" * 60)

    print("  创建第二个托盘 TRAY-FIX-002 做问题3测试")
    resp = requests.post(f'{BASE_URL}/trays/', json={
        'tray_code': 'TRAY-FIX-002',
        'capacity': 100,
        'area': '修复测试区',
        'applicable_sessions': '场次A',
        'responsible_person': '测试员',
        'status': 'pending_pickup'
    })
    if resp.status_code != 201:
        resp = requests.get(f'{BASE_URL}/trays/?search=TRAY-FIX-002')
        tray2 = resp.json()['results'][0]
        tray2_id = tray2['id']
    else:
        tray2 = resp.json()
        tray2_id = tray2['id']

    print("  领取 -> 归还 -> 清点(零差异，待确认状态)")
    requests.post(f'{BASE_URL}/trays/pickup/', json={'tray_id': tray2_id, 'session': '场次A', 'receiver': '测试人'})
    requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray2_id})
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray2_id, 'actual_count': 100, 'expected_count': 100,
        'diff_description': '无差异'
    })
    inv_zero_id = resp.json()['inventory']['id']
    print(f"  差异数量: {resp.json()['inventory']['diff_count']}")
    print(f"  托盘状态: {resp.json()['tray']['status_display']}")

    print("\n  尝试以'清点差异'来源登记零差异清点 -> 应被拦截")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray2_id,
        'inventory_record_id': inv_zero_id,
        'source': 'inventory_diff',
        'handler': '处理人B',
        'description': '测试零差异登记'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 零差异清点不能登记为'清点差异'来源")
    else:
        print("  ❌ 零差异清点仍能登记为'清点差异'来源！")

    print("\n  尝试以'观察状态'来源在未观察状态托盘上登记 -> 应被拦截")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray2_id,
        'inventory_record_id': inv_zero_id,
        'source': 'observing_status',
        'handler': '处理人B',
        'description': '测试非观察状态登记'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 非观察状态托盘不能登记为'观察状态'来源")
    else:
        print("  ❌ 非观察状态托盘仍能登记为'观察状态'来源！")

    print("\n  尝试以'清点差异'来源不指定清点记录 -> 应被拦截")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray2_id,
        'source': 'inventory_diff',
        'handler': '处理人B',
        'description': '测试不指定清点记录'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 清点差异来源必须指定清点记录")
    else:
        print("  ❌ 清点差异来源未指定清点记录也能登记！")

    print("\n" + "=" * 60)
    print("问题4: 已处理异常数量应包含已处理+已关闭")
    print("=" * 60)

    print("  关闭第一个异常单(已处理状态 -> 已关闭)")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/close/')
    print(f"  关闭状态码: {resp.status_code}")
    print(f"  异常状态: {resp.json()['status_display']}")

    print("\n  查看异常统计接口:")
    resp = requests.get(f'{BASE_URL}/abnormals/stats/overview/')
    stats = resp.json()
    print(f"  待处理: {stats['pending_count']}")
    print(f"  已处理(resolved+closed): {stats['resolved_count']}")
    print(f"  已关闭: {stats['closed_count']}")

    print("\n  查看托盘概览统计:")
    resp = requests.get(f'{BASE_URL}/trays/stats/overview/')
    tray_stats = resp.json()
    print(f"  abnormal_pending_count: {tray_stats.get('abnormal_pending_count')}")
    print(f"  abnormal_resolved_count(应包含关闭): {tray_stats.get('abnormal_resolved_count')}")

    if stats['resolved_count'] >= 1 and tray_stats.get('abnormal_resolved_count', 0) >= 1:
        print("  ✅ 问题4修复: 已处理数量包含已关闭的异常单")
    else:
        print("  ❌ 问题4未修复: 已关闭异常单不算已处理")

    print("\n" + "=" * 60)
    print("所有问题修复验证完成")
    print("=" * 60)


if __name__ == '__main__':
    test_all_fixes()
