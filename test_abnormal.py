import requests

resp = requests.get('http://127.0.0.1:8124/api/trays/stats/abnormal-records/')
print('Status:', resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    print('High diff records:', len(data['high_diff_records']))
    print('Pending confirm:', data['pending_confirm_count'])
    print('Missing conclusion:', data['missing_conclusion_count'])
    print('Consecutive diff persons:', data['consecutive_diff_persons'])
    if data['high_diff_records']:
        print('First high diff:', data['high_diff_records'][0]['diff_count'])
else:
    print('Error:', resp.text[:500])
