import requests
import json

BASE_URL = 'http://127.0.0.1:8124/api'

def test_api():
    print("=== 1. 创建托盘 ===")
    tray_data = {
        'tray_code': 'TRAY-001',
        'capacity': 50,
        'area': 'A区',
        'applicable_sessions': '场次1,场次2,场次3',
        'responsible_person': '张三',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    print(f"创建托盘: {resp.status_code} - {resp.json()}")
    tray_id = resp.json()['id']
    
    tray2 = {
        'tray_code': 'TRAY-002',
        'capacity': 50,
        'area': 'B区',
        'applicable_sessions': '场次1,场次2',
        'responsible_person': '李四',
        'status': 'pending_pickup'
    }
    resp2 = requests.post(f'{BASE_URL}/trays/', json=tray2)
    print(f"创建托盘2: {resp2.status_code}")
    
    print("\n=== 2. 领取托盘 ===")
    pickup_data = {
        'tray_id': tray_id,
        'session': '场次1',
        'receiver': '王五'
    }
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json=pickup_data)
    print(f"领取托盘: {resp.status_code} - {resp.json()}")
    
    print("\n=== 3. 尝试重复领取 (应该失败) ===")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json=pickup_data)
    print(f"重复领取: {resp.status_code} - {resp.json()}")
    
    print("\n=== 4. 归还托盘 ===")
    return_data = {'tray_id': tray_id}
    resp = requests.post(f'{BASE_URL}/trays/return_tray/', json=return_data)
    print(f"归还托盘: {resp.status_code} - {resp.json()}")
    
    print("\n=== 5. 清点托盘 (小差异) ===")
    inventory_data = {
        'tray_id': tray_id,
        'actual_count': 48,
        'expected_count': 50,
        'diff_description': '少了2张'
    }
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json=inventory_data)
    print(f"清点结果: {resp.status_code}")
    result = resp.json()
    print(f"  托盘状态: {result['tray']['status_display']}")
    print(f"  差异数量: {result['inventory']['diff_count']}")
    inventory_id = result['inventory']['id']
    
    print("\n=== 6. 确认清点结果 ===")
    confirm_data = {
        'inventory_id': inventory_id,
        'confirmer': '管理员',
        'conclusion': '正常损耗，已确认'
    }
    resp = requests.post(f'{BASE_URL}/trays/confirm/', json=confirm_data)
    print(f"确认结果: {resp.status_code}")
    result = resp.json()
    print(f"  托盘状态: {result['tray']['status_display']}")
    print(f"  确认状态: {result['inventory']['confirm_status_display']}")
    
    print("\n=== 7. 清点大差异 (超过阈值，转入观察中) ===")
    # 先再领出归还一次
    requests.post(f'{BASE_URL}/trays/pickup/', json={'tray_id': tray_id, 'session': '场次2', 'receiver': '赵六'})
    requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    
    big_diff_data = {
        'tray_id': tray_id,
        'actual_count': 40,
        'expected_count': 50,
        'diff_description': '差异较大，需要调查'
    }
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json=big_diff_data)
    print(f"大差异清点: {resp.status_code}")
    result = resp.json()
    print(f"  托盘状态: {result['tray']['status_display']}")
    print(f"  差异数量: {result['inventory']['diff_count']}")
    
    print("\n=== 8. 统计概览 ===")
    resp = requests.get(f'{BASE_URL}/trays/stats/overview/')
    print(f"概览数据: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    
    print("\n=== 9. 按天趋势 ===")
    resp = requests.get(f'{BASE_URL}/trays/stats/daily-trend/?days=7')
    print(f"趋势数据: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    
    print("\n=== 10. 异常记录 ===")
    resp = requests.get(f'{BASE_URL}/trays/stats/abnormal-records/')
    print(f"异常记录: {resp.status_code}")
    data = resp.json()
    print(f"  高差异记录数: {len(data['high_diff_records'])}")
    print(f"  晚归记录数: {len(data['late_returns'])}")
    print(f"  连续差异责任人: {data['consecutive_diff_persons']}")
    print(f"  缺确认结论数: {data['missing_conclusion_count']}")
    print(f"  待确认数: {data['pending_confirm_count']}")
    
    print("\n=== 11. 查询筛选 - 按区域 ===")
    resp = requests.get(f'{BASE_URL}/trays/?area=A')
    print(f"A区托盘: {resp.status_code}")
    print(f"  数量: {len(resp.json()['results'])}")
    
    print("\n=== 12. 区域周转效率 ===")
    resp = requests.get(f'{BASE_URL}/trays/stats/area-efficiency/')
    print(f"区域效率: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))

if __name__ == '__main__':
    test_api()
