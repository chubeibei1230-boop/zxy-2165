import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:8124/api'


def test_abnormal_handling():
    print("=" * 60)
    print("托盘异常处理闭环模块测试")
    print("=" * 60)

    print("\n【1. 创建测试托盘】")
    tray_data = {
        'tray_code': 'TRAY-ABNORMAL-001',
        'capacity': 100,
        'area': '异常测试区',
        'applicable_sessions': '场次A,场次B',
        'responsible_person': '测试责任人',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    if resp.status_code == 201:
        tray_id = resp.json()['id']
        print(f"  创建成功 ID={tray_id}")
    else:
        resp = requests.get(f'{BASE_URL}/trays/?search=TRAY-ABNORMAL-001')
        results = resp.json()['results']
        if results:
            tray_id = results[0]['id']
            print(f"  已存在 ID={tray_id}")
        else:
            print("  无法创建托盘，测试终止")
            return

    print("\n【2. 正常状态托盘不应允许登记异常处理单】")
    abnormal_data = {
        'tray_id': tray_id,
        'source': 'inventory_diff',
        'handler': '处理人A',
        'description': '测试异常'
    }
    resp = requests.post(f'{BASE_URL}/abnormals/', json=abnormal_data)
    print(f"  待领取状态登记异常 -> 状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 正常状态托盘无法登记异常处理单")
    else:
        print("  ❌ 正常状态托盘不应允许登记异常处理单！")

    print("\n【3. 完整流程: 领取 -> 归还 -> 清点(大差异进入观察) -> 登记异常 -> 处理 -> 关闭】")

    print("  步骤1: 领取托盘")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '场次A', 'receiver': '领取人'
    })
    print(f"    状态码: {resp.status_code}, 托盘状态: {resp.json()['tray']['status_display']}")

    print("  步骤2: 归还托盘")
    resp = requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    print(f"    状态码: {resp.status_code}, 托盘状态: {resp.json()['tray']['status_display']}")
    latest_record = resp.json().get('record')
    tray_record_id = latest_record['id'] if latest_record else None

    print("  步骤3: 清点(大差异 -> 进入观察)")
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray_id,
        'actual_count': 85,
        'expected_count': 100,
        'diff_description': '差异较大，需要调查原因'
    })
    print(f"    状态码: {resp.status_code}")
    if resp.status_code == 200:
        inv_data = resp.json()
        inventory_id = inv_data['inventory']['id']
        print(f"    托盘状态: {inv_data['tray']['status_display']}, 差异: {inv_data['inventory']['diff_count']}")
        assert inv_data['tray']['status'] == 'observing', "大差异应进入观察状态"
        print("    ✅ 大差异正确进入观察状态")
    else:
        print(f"    ❌ 清点失败: {resp.json()}")
        return

    print("\n【4. 观察状态托盘登记异常处理单】")
    abnormal_data = {
        'tray_id': tray_id,
        'inventory_record_id': inventory_id,
        'tray_record_id': tray_record_id,
        'source': 'inventory_diff',
        'handler': '处理人A',
        'measures': '调查原因，联系相关人员',
        'expected_completion_time': (datetime.now() + timedelta(days=2)).isoformat(),
        'description': '清点差异15张，超过阈值，需要调查'
    }
    resp = requests.post(f'{BASE_URL}/abnormals/', json=abnormal_data)
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 201:
        abnormal_id = resp.json()['id']
        print(f"  异常处理单ID: {abnormal_id}")
        print(f"  来源: {resp.json()['source_display']}")
        print(f"  状态: {resp.json()['status_display']}")
        print("  ✅ 异常处理单创建成功")
    else:
        print(f"  ❌ 创建失败: {resp.json()}")
        return

    print("\n【5. 查看异常处理单详情（关联展示托盘、领还记录、清点记录）】")
    resp = requests.get(f'{BASE_URL}/abnormals/{abnormal_id}/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        detail = resp.json()
        has_tray_detail = 'tray_detail' in detail and detail['tray_detail'] is not None
        has_inv_detail = 'inventory_record_detail' in detail and detail['inventory_record_detail'] is not None
        has_record_detail = 'tray_record_detail' in detail and detail['tray_record_detail'] is not None
        print(f"  托盘详情: {'✅' if has_tray_detail else '❌'}")
        print(f"  清点记录详情: {'✅' if has_inv_detail else '❌'}")
        print(f"  领还记录详情: {'✅' if has_record_detail else '❌'}")
    else:
        print(f"  ❌ 获取详情失败: {resp.json()}")

    print("\n【6. 按条件查询异常处理单】")
    resp = requests.get(f'{BASE_URL}/abnormals/?tray_id={tray_id}')
    print(f"  按托盘ID查询: {resp.status_code}, 结果数: {resp.json()['count']}")
    resp = requests.get(f'{BASE_URL}/abnormals/?area=异常测试')
    print(f"  按区域查询: {resp.status_code}, 结果数: {resp.json()['count']}")
    resp = requests.get(f'{BASE_URL}/abnormals/?handler=处理人')
    print(f"  按责任人查询: {resp.status_code}, 结果数: {resp.json()['count']}")
    resp = requests.get(f'{BASE_URL}/abnormals/?status=pending')
    print(f"  按状态查询: {resp.status_code}, 结果数: {resp.json()['count']}")

    print("\n【7. 开始处理异常】")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/start_processing/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  处理状态: {resp.json()['status_display']}")
        print("  ✅ 异常开始处理")
    else:
        print(f"  ❌ 开始处理失败: {resp.json()}")

    print("\n【8. 不能重复开始处理】")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/start_processing/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print("  ✅ 重复开始处理被拦截")
    else:
        print("  ❌ 重复开始处理未被拦截")

    print("\n【9. 处理完成（resolve），推动托盘恢复可用】")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/resolve/', json={
        'result': '已查明原因，客户带走忘记归还，已追回8张，剩余7张补齐',
        'measures': '联系客户追回，补齐差异数量'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  异常状态: {data['abnormal']['status_display']}")
        print(f"  托盘状态: {data['tray']['status_display']}")
        if data['tray']['status'] == 'available':
            print("  ✅ 处理完成后托盘自动恢复可用")
        else:
            print("  ⚠️ 托盘尚未恢复可用（可能还有待确认的清点记录）")
            print("  需要先确认清点记录...")
            resp2 = requests.post(f'{BASE_URL}/trays/confirm/', json={
                'inventory_id': inventory_id,
                'confirmer': '管理员',
                'conclusion': '异常已处理，确认清点结果'
            })
            print(f"  确认清点: {resp2.status_code}")
            if resp2.status_code == 200:
                print(f"  确认后托盘状态: {resp2.json()['tray']['status_display']}")
                if resp2.json()['tray']['status'] == 'available':
                    print("  ✅ 确认后托盘恢复可用")
    else:
        print(f"  ❌ 处理完成失败: {resp.json()}")

    print("\n【10. 关闭异常处理单】")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/close/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  异常状态: {resp.json()['status_display']}")
        print("  ✅ 异常处理单已关闭")
    else:
        print(f"  ❌ 关闭失败: {resp.json()}")

    print("\n【11. 不能重复关闭】")
    resp = requests.post(f'{BASE_URL}/abnormals/{abnormal_id}/close/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print("  ✅ 重复关闭被拦截")
    else:
        print("  ❌ 重复关闭未被拦截")

    print("\n【12. 恢复可用后可以再次领取（闭环验证）】")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '场次B', 'receiver': '领取人2'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  托盘状态: {resp.json()['tray']['status_display']}")
        print("  ✅ 恢复后可正常领取，闭环完整")
    else:
        print(f"  ❌ 领取失败: {resp.json()}")

    print("\n【13. 异常处理统计接口】")
    resp = requests.get(f'{BASE_URL}/abnormals/stats/overview/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"  待处理数量: {stats['pending_count']}")
        print(f"  已处理数量: {stats['resolved_count']}")
        print(f"  已关闭数量: {stats['closed_count']}")
        print(f"  逾期数量: {stats['overdue_count']}")
        print(f"  区域分布: {json.dumps(stats['area_distribution'], ensure_ascii=False)}")
        print(f"  来源分布: {json.dumps(stats['source_distribution'], ensure_ascii=False)}")
        print("  ✅ 异常统计接口正常")
    else:
        print(f"  ❌ 统计接口失败: {resp.json()}")

    print("\n【14. 托盘概览统计中包含异常信息】")
    resp = requests.get(f'{BASE_URL}/trays/stats/overview/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"  异常待处理数: {stats.get('abnormal_pending_count', 'N/A')}")
        print(f"  异常已处理数: {stats.get('abnormal_resolved_count', 'N/A')}")
        print(f"  异常区域分布: {json.dumps(stats.get('abnormal_area_distribution', []), ensure_ascii=False)}")
        print("  ✅ 概览统计已包含异常信息")
    else:
        print(f"  ❌ 概览统计失败")

    print("\n【15. 测试不同来源的异常处理单】")
    resp = requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    if resp.status_code == 200:
        resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
            'tray_id': tray_id,
            'actual_count': 50,
            'expected_count': 100,
            'diff_description': '大面积丢失'
        })
        if resp.status_code == 200:
            inv_id2 = resp.json()['inventory']['id']
            abnormal_data2 = {
                'tray_id': tray_id,
                'inventory_record_id': inv_id2,
                'source': 'observing_status',
                'handler': '处理人B',
                'description': '观察状态异常，需要持续跟踪',
            }
            resp = requests.post(f'{BASE_URL}/abnormals/', json=abnormal_data2)
            print(f"  观察状态来源异常处理单: {resp.status_code}")
            if resp.status_code == 201:
                print(f"  ✅ 观察状态来源异常处理单创建成功")
            else:
                print(f"  ❌ 创建失败: {resp.json()}")

    print("\n" + "=" * 60)
    print("托盘异常处理闭环模块测试完成")
    print("=" * 60)


if __name__ == '__main__':
    test_abnormal_handling()
