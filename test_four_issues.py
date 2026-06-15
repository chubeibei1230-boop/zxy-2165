import requests
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:8124/api'


def test_all_four_issues():
    print("=" * 70)
    print("四个问题修复验证测试")
    print("=" * 70)

    print("\n【准备测试数据】")
    print("-" * 70)

    tray_data = {
        'tray_code': 'FIX-TEST-SMALL-001',
        'capacity': 100,
        'area': '修复测试区',
        'applicable_sessions': '早场,午场',
        'responsible_person': '测试员A',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    if resp.status_code != 201:
        resp = requests.get(f'{BASE_URL}/trays/?search=FIX-TEST-SMALL-001')
        tray = resp.json()['results'][0]
    else:
        tray = resp.json()
    tray_id = tray['id']
    print(f"  已创建小差异测试托盘: {tray['tray_code']} (ID: {tray_id})")

    print("\n" + "=" * 70)
    print("问题1: 小差异托盘有待处理异常时，直接确认会绕过责任闭环")
    print("=" * 70)

    print("\n  领取 -> 归还 -> 清点(小差异，待确认状态)")
    requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '早场', 'receiver': '测试人1'
    })
    requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray_id, 'actual_count': 98, 'expected_count': 100,
        'diff_description': '短少2个，小差异'
    })
    inv_id = resp.json()['inventory']['id']
    tray_status = resp.json()['tray']['status']
    print(f"  清点后托盘状态: {resp.json()['tray']['status_display']}")
    print(f"  差异数量: {resp.json()['inventory']['diff_count']}")

    print("\n  登记异常处理单（小差异）")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray_id,
        'inventory_record_id': inv_id,
        'source': 'inventory_diff',
        'handler': '处理人B',
        'description': '小差异也登记异常，测试闭环',
        'expected_completion_time': (datetime.now() + timedelta(hours=24)).isoformat()
    })
    abn_id = resp.json()['id']
    print(f"  异常单ID: {abn_id}, 状态: {resp.json()['status_display']}")
    print(f"  自动关联领还记录: {resp.json().get('tray_record_id') is not None}")

    print("\n  尝试直接确认清点记录 -> 应该被拦截")
    resp = requests.post(f'{BASE_URL}/trays/confirm/', json={
        'inventory_id': inv_id,
        'confirmer': '管理员',
        'conclusion': '跳过异常直接确认'
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  错误信息: {resp.json()['detail']}")
        print("  ✅ 问题1修复: 小差异托盘有待处理异常时不能直接确认")
    else:
        print("  ❌ 问题1未修复: 有未处理异常仍能直接确认！")

    print("\n" + "=" * 70)
    print("问题2: 小差异异常resolve后托盘停留在待确认，不能继续领取")
    print("=" * 70)

    print("\n  开始处理 -> resolve 异常")
    requests.post(f'{BASE_URL}/abnormals/{abn_id}/start_processing/')
    resp = requests.post(f'{BASE_URL}/abnormals/{abn_id}/resolve/', json={
        'result': '已查明原因，操作人补齐',
        'measures': '加强培训'
    })
    print(f"  resolve 状态码: {resp.status_code}")
    print(f"  异常状态: {resp.json()['abnormal']['status_display']}")
    print(f"  托盘状态: {resp.json()['tray']['status_display']}")

    tray_status_after = resp.json()['tray']['status']
    if tray_status_after == 'available':
        print("  ✅ 问题2修复: 小差异异常resolve后托盘恢复可用")
    else:
        print(f"  ❌ 问题2未修复: 托盘状态还是 {tray_status_after}")

    print("\n  验证托盘可以再次领取(闭环):")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '午场', 'receiver': '测试人2'
    })
    if resp.status_code == 200:
        print("  ✅ 托盘可以正常领取，闭环完整")
        requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    else:
        print(f"  ❌ 领取失败: {resp.json()}")

    print("\n" + "=" * 70)
    print("问题3: 场次统计接口带场次筛选会报500")
    print("=" * 70)

    print("\n  不带场次筛选:")
    resp = requests.get(f'{BASE_URL}/review/stats/by-session/')
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  场次数量: {len(data)}")

    print("\n  带场次筛选(早场):")
    resp = requests.get(f'{BASE_URL}/review/stats/by-session/', params={'session': '早场'})
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  筛选后场次数量: {len(data)}")
        print("  ✅ 问题3修复: 带场次筛选正常返回")
    else:
        print(f"  ❌ 问题3未修复: {resp.text[:200]}")

    print("\n  带场次筛选(午场):")
    resp = requests.get(f'{BASE_URL}/review/stats/by-session/', params={'session': '午场'})
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        print("  ✅ 午场筛选也正常")

    print("\n" + "=" * 70)
    print("问题4: 异常登记时只传清点记录不传领还记录")
    print("=" * 70)

    print("\n  准备另一个小差异清点记录")
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray_id, 'actual_count': 97, 'expected_count': 100,
        'diff_description': '又少了3个'
    })
    inv2_id = resp.json()['inventory']['id']
    print(f"  清点记录ID: {inv2_id}")

    print("\n  只传 inventory_record_id，不传 tray_record_id:")
    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray_id,
        'inventory_record_id': inv2_id,
        'source': 'inventory_diff',
        'handler': '处理人C',
        'description': '只传清点记录，测试自动关联领还记录',
    })
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 201:
        data = resp.json()
        has_tray_record = data.get('tray_record_id') is not None
        session = data.get('session') or (data.get('tray_record_detail', {}) or {}).get('session')
        print(f"  异常单ID: {data['id']}")
        print(f"  关联的领还记录ID: {data.get('tray_record_id')}")
        if data.get('tray_record_id'):
            print("  ✅ 问题4修复: 只传清点记录时自动关联领还记录")
        else:
            print("  ❌ 问题4未修复: 没有自动关联领还记录")
    else:
        print(f"  ❌ 异常登记失败: {resp.text[:200]}")

    print("\n" + "=" * 70)
    print("所有四个问题修复验证完成")
    print("=" * 70)


if __name__ == '__main__':
    test_all_four_issues()
