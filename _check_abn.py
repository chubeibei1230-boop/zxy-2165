import requests
BASE_URL = 'http://127.0.0.1:8124/api'

resp = requests.get(f'{BASE_URL}/abnormals/5/')
if resp.status_code == 200:
    data = resp.json()
    print('异常单详情 - 托盘相关字段:')
    for k, v in data.items():
        if 'tray' in k:
            print(f'  {k}: {v}')
    print()
    tray_rec = data.get('tray_record')
    print(f'tray_record 字段: {tray_rec}')
    print()
    if data.get('tray_record_detail'):
        print('tray_record_detail:')
        for k, v in data['tray_record_detail'].items():
            print(f'  {k}: {v}')
else:
    print(f'Error: {resp.status_code}')
    print(resp.text[:500])
