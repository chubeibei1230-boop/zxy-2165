import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:8124/api'


def test_review_module():
    print("=" * 70)
    print("托盘异常复盘与责任闭环模块 - 接口测试")
    print("=" * 70)

    print("\n【1/7】准备测试数据 - 创建托盘并完成完整业务流程")
    print("-" * 70)

    tray_data = {
        'tray_code': 'REVIEW-TEST-001',
        'capacity': 100,
        'area': '复盘测试区A',
        'applicable_sessions': '早场,午场,晚场',
        'responsible_person': '张三',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    if resp.status_code != 201:
        resp = requests.get(f'{BASE_URL}/trays/?search=REVIEW-TEST-001')
        tray = resp.json()['results'][0]
    else:
        tray = resp.json()
    tray_id = tray['id']
    print(f"  已创建托盘: {tray['tray_code']} (ID: {tray_id})")

    tray_data2 = {
        'tray_code': 'REVIEW-TEST-002',
        'capacity': 80,
        'area': '复盘测试区B',
        'applicable_sessions': '早场,午场',
        'responsible_person': '李四',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data2)
    if resp.status_code != 201:
        resp = requests.get(f'{BASE_URL}/trays/?search=REVIEW-TEST-002')
        tray2 = resp.json()['results'][0]
    else:
        tray2 = resp.json()
    tray2_id = tray2['id']
    print(f"  已创建托盘: {tray2['tray_code']} (ID: {tray2_id})")

    print("\n  托盘1完整流程: 领取 -> 归还 -> 清点(大差异) -> 登记异常 -> 处理 -> 关闭")
    requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '早场', 'receiver': '王五'
    })
    requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray_id, 'actual_count': 88, 'expected_count': 100,
        'diff_description': '短少12个'
    })
    inv1_id = resp.json()['inventory']['id']
    print(f"  清点完成，差异: {resp.json()['inventory']['diff_count']}")

    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray_id,
        'inventory_record_id': inv1_id,
        'source': 'inventory_diff',
        'handler': '张三',
        'measures': '追查原因，联系责任人',
        'description': '短少12个托盘，需调查',
        'expected_completion_time': (datetime.now() + timedelta(hours=2)).isoformat()
    })
    abn1_id = resp.json()['id']
    print(f"  异常登记完成 (ID: {abn1_id})")

    requests.post(f'{BASE_URL}/abnormals/{abn1_id}/start_processing/')
    resp = requests.post(f'{BASE_URL}/abnormals/{abn1_id}/resolve/', json={
        'result': '已查明为操作失误，责任人补齐',
        'measures': '培训操作流程'
    })
    requests.post(f'{BASE_URL}/abnormals/{abn1_id}/close/')
    print("  异常已处理并关闭")

    print("\n  托盘2流程: 领取 -> 归还 -> 清点(中差异) -> 登记异常(未处理)")
    requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray2_id, 'session': '午场', 'receiver': '赵六'
    })
    requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray2_id})
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray2_id, 'actual_count': 75, 'expected_count': 80,
        'diff_description': '短少5个'
    })
    inv2_id = resp.json()['inventory']['id']

    resp = requests.post(f'{BASE_URL}/abnormals/', json={
        'tray_id': tray2_id,
        'inventory_record_id': inv2_id,
        'source': 'inventory_diff',
        'handler': '李四',
        'description': '短少5个托盘，待处理',
        'expected_completion_time': (datetime.now() - timedelta(hours=1)).isoformat()
    })
    abn2_id = resp.json()['id']
    print(f"  已登记待处理异常 (ID: {abn2_id})，已设置为逾期")

    print("\n【2/7】测试复盘概览接口 GET /api/review/overview/")
    print("-" * 70)
    resp = requests.get(f'{BASE_URL}/review/overview/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 接口调用成功")
        print(f"  异常总数: {data['abnormal_stats']['total']}")
        print(f"  待处理: {data['abnormal_stats']['pending']}")
        print(f"  处理中: {data['abnormal_stats']['processing']}")
        print(f"  已处理: {data['abnormal_stats']['resolved']}")
        print(f"  已关闭: {data['abnormal_stats']['closed']}")
        print(f"  逾期: {data['abnormal_stats']['overdue']}")
        print(f"  解决率: {data['abnormal_stats']['resolution_rate']}%")
        print(f"  差异记录数: {data['diff_stats']['record_count']}")
        print(f"  差异总量: {data['diff_stats']['total_amount']}")
        print(f"  来源分布: {len(data['source_distribution'])} 类")
        print(f"  状态分布: {len(data['status_distribution'])} 类")
        print(f"\n  返回结构字段: {list(data.keys())}")
    else:
        print(f"  ❌ 接口失败: {resp.status_code} {resp.text}")

    print("\n【3/7】测试差异明细接口 GET /api/review/diff-details/")
    print("-" * 70)
    resp = requests.get(f'{BASE_URL}/review/diff-details/')
    if resp.status_code == 200:
        data = resp.json()
        results = data.get('results', data)
        print(f"  ✅ 接口调用成功，共 {len(results)} 条差异记录")
        if results:
            item = results[0]
            print(f"  首条记录字段: {list(item.keys())}")
            print(f"  托盘编号: {item['tray_code']}")
            print(f"  区域: {item['tray_area']}")
            print(f"  责任人: {item['tray_responsible_person']}")
            print(f"  场次: {item.get('session')}")
            print(f"  差异数量: {item['diff_count']}")
            print(f"  是否有关联异常: {item['has_abnormal']}")
            if item['has_abnormal']:
                print(f"  异常状态: {item['abnormal_status_display']}")
                print(f"  异常处理人: {item['abnormal_handler']}")
    else:
        print(f"  ❌ 接口失败: {resp.status_code} {resp.text}")

    print("\n  带过滤参数测试 - 按区域过滤:")
    resp = requests.get(f'{BASE_URL}/review/diff-details/', params={'area': '复盘测试区A'})
    if resp.status_code == 200:
        data = resp.json()
        results = data.get('results', data)
        print(f"  ✅ 区域过滤成功，共 {len(results)} 条记录")

    print("\n【4/7】测试异常列表接口 GET /api/review/abnormal-list/")
    print("-" * 70)
    resp = requests.get(f'{BASE_URL}/review/abnormal-list/')
    if resp.status_code == 200:
        data = resp.json()
        results = data.get('results', data)
        print(f"  ✅ 接口调用成功，共 {len(results)} 条异常记录")
        if results:
            item = results[0]
            print(f"  首条记录字段: {list(item.keys())}")
            print(f"  托盘编号: {item['tray_code']}")
            print(f"  异常来源: {item['source_display']}")
            print(f"  处理状态: {item['status_display']}")
            print(f"  是否逾期: {item['is_overdue']}")
            print(f"  处理责任人: {item['handler']}")
    else:
        print(f"  ❌ 接口失败: {resp.status_code} {resp.text}")

    print("\n  按逾期状态过滤测试:")
    resp = requests.get(f'{BASE_URL}/review/abnormal-list/', params={'is_overdue': 'true'})
    if resp.status_code == 200:
        data = resp.json()
        results = data.get('results', data)
        print(f"  ✅ 逾期异常过滤成功，共 {len(results)} 条")

    print("\n【5/7】测试维度统计接口")
    print("-" * 70)

    print("\n  5.1 按托盘维度 GET /api/review/stats/by-tray/")
    resp = requests.get(f'{BASE_URL}/review/stats/by-tray/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 成功，共 {len(data)} 个托盘统计")
        if data:
            item = data[0]
            print(f"  首条字段: {list(item.keys())}")
            print(f"  托盘: {item['tray_code']}, 异常总数: {item['abnormal_total']}, "
                  f"待处理: {item['abnormal_pending']}, 逾期: {item['abnormal_overdue']}")
    else:
        print(f"  ❌ 失败: {resp.status_code} {resp.text}")

    print("\n  5.2 按区域维度 GET /api/review/stats/by-area/")
    resp = requests.get(f'{BASE_URL}/review/stats/by-area/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 成功，共 {len(data)} 个区域统计")
        if data:
            item = data[0]
            print(f"  首条字段: {list(item.keys())}")
            print(f"  区域: {item['area']}, 托盘数: {item['tray_count']}, "
                  f"异常总数: {item['abnormal_total']}")
    else:
        print(f"  ❌ 失败: {resp.status_code} {resp.text}")

    print("\n  5.3 按责任人维度 GET /api/review/stats/by-person/")
    resp = requests.get(f'{BASE_URL}/review/stats/by-person/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 成功，共 {len(data)} 个责任人统计")
        if data:
            item = data[0]
            print(f"  首条字段: {list(item.keys())}")
            print(f"  责任人: {item['responsible_person']}, 托盘数: {item['tray_count']}, "
                  f"异常总数: {item['abnormal_total']}")
    else:
        print(f"  ❌ 失败: {resp.status_code} {resp.text}")

    print("\n  5.4 按场次维度 GET /api/review/stats/by-session/")
    resp = requests.get(f'{BASE_URL}/review/stats/by-session/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 成功，共 {len(data)} 个场次统计")
        if data:
            item = data[0]
            print(f"  首条字段: {list(item.keys())}")
            print(f"  场次: {item['session']}, 领还记录数: {item['record_count']}, "
                  f"异常数: {item['abnormal_total']}")
    else:
        print(f"  ❌ 失败: {resp.status_code} {resp.text}")

    print("\n【6/7】测试待跟进事项接口 GET /api/review/pending-items/")
    print("-" * 70)
    resp = requests.get(f'{BASE_URL}/review/pending-items/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 接口调用成功")
        print(f"  待处理异常数: {data['pending_abnormal_count']}")
        print(f"  待确认清点数: {data['pending_confirm_count']}")
        print(f"  逾期异常数: {data['overdue_abnormal_count']}")
        print(f"  待处理异常列表: {len(data['pending_abnormals'])} 条")
        print(f"  待确认清点列表: {len(data['pending_confirms'])} 条")
    else:
        print(f"  ❌ 接口失败: {resp.status_code} {resp.text}")

    print("\n【7/7】测试托盘流转轨迹接口 GET /api/review/{tray_id}/trajectory/")
    print("-" * 70)
    resp = requests.get(f'{BASE_URL}/review/{tray_id}/trajectory/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ 接口调用成功")
        print(f"  托盘编号: {data['tray_code']}")
        print(f"  当前状态: {data['current_status_display']}")
        print(f"  总事件数: {data['total_events']}")
        print(f"  总异常数: {data['total_abnormal']}")
        print(f"  待处理异常数: {data['pending_abnormal']}")
        print(f"\n  流转事件时间线:")
        for evt in data['events']:
            print(f"    [{evt['event_time'][:19]}] {evt['event_type_display']}"
                  f" - {evt['description']}"
                  f" (操作人: {evt['operator'] or '系统'})")
        print(f"\n  事件类型分布:")
        event_types = {}
        for evt in data['events']:
            event_types[evt['event_type_display']] = event_types.get(evt['event_type_display'], 0) + 1
        for etype, cnt in event_types.items():
            print(f"    - {etype}: {cnt} 次")
    else:
        print(f"  ❌ 接口失败: {resp.status_code} {resp.text}")

    print("\n" + "=" * 70)
    print("验证: 现有托盘状态流转和异常处理流程未受影响")
    print("=" * 70)

    print("\n  测试托盘正常领取:")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={
        'tray_id': tray_id, 'session': '午场', 'receiver': '测试员'
    })
    if resp.status_code == 200:
        print(f"  ✅ 托盘可正常领取，状态: {resp.json()['tray']['status_display']}")
        requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    else:
        print(f"  ❌ 领取失败: {resp.text}")

    print("\n  测试异常单正常创建:")
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json={
        'tray_id': tray2_id, 'actual_count': 70, 'expected_count': 80,
        'diff_description': '又少了10个'
    })
    if resp.status_code == 200:
        inv_id = resp.json()['inventory']['id']
        resp = requests.post(f'{BASE_URL}/abnormals/', json={
            'tray_id': tray2_id,
            'inventory_record_id': inv_id,
            'source': 'inventory_diff',
            'handler': '李四',
            'description': '继续短少测试'
        })
        if resp.status_code == 201:
            print(f"  ✅ 异常单可正常创建 (ID: {resp.json()['id']})")
        else:
            print(f"  ❌ 异常单创建失败: {resp.text}")
    else:
        print(f"  ❌ 清点失败: {resp.text}")

    print("\n" + "=" * 70)
    print("所有测试完成！")
    print("=" * 70)


if __name__ == '__main__':
    test_review_module()
