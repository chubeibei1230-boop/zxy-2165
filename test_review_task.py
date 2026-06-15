import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://127.0.0.1:8124/api'


def test_review_task_module():
    print("=" * 70)
    print("托盘异常复核任务模块 - 接口测试")
    print("=" * 70)

    print("\n【1/8】准备测试数据 - 创建托盘")
    print("-" * 70)

    tray_code = f'RT-TEST-{datetime.now().strftime("%H%M%S")}'
    tray_data = {
        'tray_code': tray_code,
        'capacity': 100,
        'area': '复核测试区',
        'applicable_sessions': '早场,午场,晚场',
        'responsible_person': '张三',
        'status': 'pending_pickup'
    }
    resp = requests.post(f'{BASE_URL}/trays/', json=tray_data)
    tray = resp.json()
    tray_id = tray['id']
    print(f"  ✓ 已创建托盘: {tray['tray_code']} (ID: {tray_id})")

    print("\n【2/8】测试创建复核任务")
    print("-" * 70)

    task_data = {
        'tray_id': tray_id,
        'source': 'manual',
        'description': '人工创建的复核测试任务',
        'priority': 'high',
        'creator': '测试员',
        'reviewer': '复核员A'
    }
    resp = requests.post(f'{BASE_URL}/review-tasks/', json=task_data)
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 201:
        task = resp.json()
        task_id = task['id']
        print(f"  ✓ 复核任务创建成功")
        print(f"    任务编号: {task['task_code']}")
        print(f"    任务状态: {task['status_display']}")
        print(f"    任务来源: {task['source_display']}")
        print(f"    复核人: {task['reviewer']}")
        print(f"    优先级: {task['priority_display']}")
    else:
        print(f"  ✗ 创建失败: {resp.json()}")
        return

    print("\n【3/8】测试复核任务列表查询")
    print("-" * 70)

    resp = requests.get(f'{BASE_URL}/review-tasks/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ 列表查询成功，共 {data['count']} 条任务")
        print(f"    本页显示: {len(data['results'])} 条")
    else:
        print(f"  ✗ 列表查询失败: {resp.status_code}")

    print("\n【4/8】测试复核任务筛选")
    print("-" * 70)

    filters = {
        'tray_code': tray_code,
        'status': 'processing',
        'priority': 'high',
    }
    resp = requests.get(f'{BASE_URL}/review-tasks/', params=filters)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ 筛选查询成功，匹配 {data['count']} 条任务")
    else:
        print(f"  ✗ 筛选查询失败: {resp.status_code}")

    print("\n【5/8】测试复核任务详情")
    print("-" * 70)

    resp = requests.get(f'{BASE_URL}/review-tasks/{task_id}/')
    if resp.status_code == 200:
        task_detail = resp.json()
        print(f"  ✓ 详情查询成功")
        print(f"    托盘信息: {task_detail['tray_detail']['tray_code']}")
        print(f"    托盘状态: {task_detail['tray_detail']['status_display']}")
    else:
        print(f"  ✗ 详情查询失败: {resp.status_code}")

    print("\n【6/8】测试指派处理人")
    print("-" * 70)

    assign_data = {'reviewer': '复核员B'}
    resp = requests.post(f'{BASE_URL}/review-tasks/{task_id}/assign/', json=assign_data)
    if resp.status_code == 200:
        task = resp.json()
        print(f"  ✓ 指派成功")
        print(f"    新复核人: {task['reviewer']}")
        print(f"    任务状态: {task['status_display']}")
    else:
        print(f"  ✗ 指派失败: {resp.status_code} - {resp.json()}")

    print("\n【7/8】测试提交复核结论")
    print("-" * 70)

    submit_data = {
        'review_result': 'false_alarm',
        'review_opinion': '经复核，该异常为误报，托盘状态正常'
    }
    resp = requests.post(f'{BASE_URL}/review-tasks/{task_id}/submit/', json=submit_data)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ 提交复核结论成功")
        print(f"    复核结论: {data['task']['review_result_display']}")
        print(f"    复核意见: {data['task']['review_opinion']}")
        print(f"    任务状态: {data['task']['status_display']}")
        print(f"    托盘状态: {data['tray']['status_display']}")
    else:
        print(f"  ✗ 提交失败: {resp.status_code} - {resp.json()}")

    print("\n【8/8】测试处理进度查询")
    print("-" * 70)

    resp = requests.get(f'{BASE_URL}/review-tasks/{task_id}/processing-progress/')
    if resp.status_code == 200:
        progress = resp.json()
        print(f"  ✓ 处理进度查询成功")
        print(f"    当前步骤: {progress['current_step']}/{progress['total_steps']}")
        print(f"    进度百分比: {progress['progress_percent']}%")
        print(f"    事件数量: {len(progress['events'])} 个")
    else:
        print(f"  ✗ 进度查询失败: {resp.status_code}")

    print("\n【补充】测试统计概览")
    print("-" * 70)

    resp = requests.get(f'{BASE_URL}/review-tasks/stats/overview/')
    if resp.status_code == 200:
        stats = resp.json()
        print(f"  ✓ 统计概览查询成功")
        print(f"    总任务数: {stats['total']}")
        print(f"    待指派: {stats['pending_assign']}")
        print(f"    处理中: {stats['processing']}")
        print(f"    已完成: {stats['completed']}")
        print(f"    已取消: {stats['cancelled']}")
        print(f"    完成率: {stats['completion_rate']}%")
    else:
        print(f"  ✗ 统计概览失败: {resp.status_code}")

    print("\n【补充】测试取消复核任务")
    print("-" * 70)

    task2_data = {
        'tray_id': tray_id,
        'source': 'manual',
        'description': '用于测试取消的任务',
        'priority': 'low',
        'creator': '测试员',
    }
    resp = requests.post(f'{BASE_URL}/review-tasks/', json=task2_data)
    if resp.status_code == 201:
        task2_id = resp.json()['id']
        cancel_data = {'cancel_reason': '测试取消功能'}
        resp = requests.post(f'{BASE_URL}/review-tasks/{task2_id}/cancel/', json=cancel_data)
        if resp.status_code == 200:
            task = resp.json()
            print(f"  ✓ 取消任务成功")
            print(f"    任务状态: {task['status_display']}")
            print(f"    取消原因: {task['cancel_reason']}")
        else:
            print(f"  ✗ 取消失败: {resp.status_code} - {resp.json()}")
    else:
        print(f"  ✗ 创建待取消任务失败")

    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)


if __name__ == '__main__':
    test_review_task_module()
