import requests
import json

BASE_URL = 'http://127.0.0.1:8124/api'

def test_fixes():
    print("=" * 60)
    print("测试修复验证")
    print("=" * 60)

    # 清理数据后创建一个新托盘用于测试
    print("\n【准备测试数据】创建新托盘 TRAY-TEST-001")
    tray_data = {
        'tray_code': 'TRAY-TEST-001',
        'capacity': 100,
        'area': '测试区',
        'applicable_sessions': '场次A,场次B',
        'responsible_person': '测试员',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    if resp.status_code != 201:
        print(f"  托盘已存在，尝试获取已有的托盘...")
        resp = requests.get(f'{BASE_URL}/trays/?search=TRAY-TEST-001')
        results = resp.json()['results']
        if results:
            tray = results[0]
            tray_id = tray['id']
            print(f"  找到已有托盘 ID={tray_id}, 状态={tray['status_display']}")
        else:
            print("  无法创建或获取托盘，测试终止")
            return
    else:
        tray = resp.json()
        tray_id = tray['id']
        print(f"  创建成功，托盘 ID={tray_id}")

    print("\n" + "-" * 60)
    print("【修复1 验证】容量上限必须大于0")
    print("-" * 60)
    bad_tray = {
        'tray_code': 'TRAY-BAD-CAP',
        'capacity': -10,
        'area': '测试区',
        'applicable_sessions': '场次A',
        'responsible_person': '测试员',
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=bad_tray)
    print(f"  创建容量为-10的托盘 -> 状态码: {resp.status_code}")
    if resp.status_code != 201:
        print(f"  错误信息: {resp.json()}")
        print("  ✅ 容量负数被拦截")
    else:
        print("  ❌ 容量负数未被拦截！")

    print("\n" + "-" * 60)
    print("【修复2 验证】不能直接通过更新接口修改状态")
    print("-" * 60)
    resp = requests.patch(f'{BASE_URL}/trays/{tray_id}/', json={'status': 'available'})
    print(f"  PATCH 修改状态 -> 状态码: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  错误信息: {resp.json()}")
        print("  ✅ 直接修改状态被拦截")
    else:
        print(f"  返回状态: {resp.json().get('status_display')}")
        print("  ❌ 直接修改状态未被拦截！")

    print("\n" + "-" * 60)
    print("【修复3 验证】领取时校验适用场次")
    print("-" * 60)
    print(f"  托盘适用场次: 场次A,场次B")

    # 先测试错误场次
    bad_session_data = {'tray_id': tray_id, 'session': '场次X', 'receiver': '测试人'}
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json=bad_session_data)
    print(f"  领取时传入不适用的场次'场次X' -> 状态码: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  错误信息: {resp.json()}")
        print("  ✅ 不适用场次被拦截")
    else:
        print("  ❌ 不适用场次未被拦截！")

    # 再测试正确场次
    good_session_data = {'tray_id': tray_id, 'session': '场次A', 'receiver': '测试人'}
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json=good_session_data)
    print(f"  领取时传入适用的场次'场次A' -> 状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  托盘当前状态: {resp.json()['tray']['status_display']}")
        print("  ✅ 适用场次可以正常领取")
    else:
        print(f"  错误信息: {resp.json()}")
        print("  ❌ 适用场次领取失败！")

    print("\n" + "-" * 60)
    print("【双重校验验证】即使状态被篡改，有未归还记录也不能领取")
    print("-" * 60)
    print("  当前托盘已经领出，再次尝试领取（同一托盘）...")
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json=good_session_data)
    print(f"  重复领取 -> 状态码: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  错误信息: {resp.json()}")
        print("  ✅ 未归还时重复领取被拦截")

    print("\n" + "-" * 60)
    print("【修复4 验证】观察中状态可以恢复可用")
    print("-" * 60)
    print("  先归还托盘 -> 清点(大差异进入观察中) -> 确认 -> 恢复可用")

    # 归还
    resp = requests.post(f'{BASE_URL}/trays/return_tray/', json={'tray_id': tray_id})
    print(f"  归还托盘 -> 状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  归还后状态: {resp.json()['tray']['status_display']}")

    # 清点 - 大差异超过阈值5
    inv_data = {
        'tray_id': tray_id,
        'actual_count': 90,
        'expected_count': 100,
        'diff_description': '丢失10张，大差异'
    }
    resp = requests.post(f'{BASE_URL}/trays/inventory/', json=inv_data)
    print(f"  清点(差异-10) -> 状态码: {resp.status_code}")
    if resp.status_code == 200:
        inv_id = resp.json()['inventory']['id']
        print(f"  清点后状态: {resp.json()['tray']['status_display']}")
        print(f"  清点记录ID: {inv_id}")

    # 确认 - 不填结论应该失败
    confirm_no_conclusion = {'inventory_id': inv_id, 'confirmer': '管理员'}
    resp = requests.post(f'{BASE_URL}/trays/confirm/', json=confirm_no_conclusion)
    print(f"  观察中确认(不填结论) -> 状态码: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  错误信息: {resp.json()}")
        print("  ✅ 观察中确认必须填写结论")

    # 确认 - 填写结论
    confirm_with_conclusion = {
        'inventory_id': inv_id,
        'confirmer': '管理员',
        'conclusion': '已查明原因，某客户带走忘记归还，已追回'
    }
    resp = requests.post(f'{BASE_URL}/trays/confirm/', json=confirm_with_conclusion)
    print(f"  观察中确认(填写结论) -> 状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  确认后托盘状态: {resp.json()['tray']['status_display']}")
        if resp.json()['tray']['status'] == 'available':
            print("  ✅ 观察中确认后成功恢复可用")
        else:
            print("  ❌ 观察中确认后未恢复可用，需要手动解除观察")
            # 测试手动解除观察接口
            tray_id_for_release = resp.json()['tray']['id']
            release_data = {
                'tray_id': tray_id_for_release,
                'operator': '管理员',
                'remark': ''
            }
            resp2 = requests.post(f'{BASE_URL}/trays/release_observing/', json=release_data)
            print(f"  解除观察(不填说明) -> 状态码: {resp2.status_code}")
            if resp2.status_code != 200:
                print(f"  错误信息: {resp2.json()}")
                print("  ✅ 解除观察必须填写处理说明")

            release_data['remark'] = '问题已处理完毕，解除观察'
            resp3 = requests.post(f'{BASE_URL}/trays/release_observing/', json=release_data)
            print(f"  解除观察(填写说明) -> 状态码: {resp3.status_code}")
            if resp3.status_code == 200:
                print(f"  解除后托盘状态: {resp3.json()['tray']['status_display']}")
                print("  ✅ 手动解除观察接口正常工作")

    # 最终确认可以再次领取
    print("\n" + "-" * 60)
    print("【最终验证】恢复可用后能否正常再次领取")
    print("-" * 60)
    resp = requests.post(f'{BASE_URL}/trays/pickup/', json={'tray_id': tray_id, 'session': '场次B', 'receiver': '测试人2'})
    print(f"  恢复可用后再次领取 -> 状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  当前状态: {resp.json()['tray']['status_display']}")
        print("  ✅ 可以正常领取，业务流程闭环完整")
    else:
        print(f"  错误信息: {resp.json()}")

    print("\n" + "=" * 60)
    print("全部修复验证完成")
    print("=" * 60)


if __name__ == '__main__':
    test_fixes()
