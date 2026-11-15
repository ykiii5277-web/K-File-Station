"""Validate the frozen archive integration after relocation, with a system-only PATH."""
from pathlib import Path
import os,shutil,subprocess,json
root=Path(__file__).resolve().parents[1]
folder=root/'build/解压 迁移/K文件处理台'
shutil.copytree(root/'dist/K文件处理台',folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('data','working','cache','*.outfiles','*.pid','*.restore','*.potfile'))
env=os.environ.copy(); env['PATH']='C:/Windows/System32;C:/Windows'
report=root/'build/archive-portable'
result=subprocess.run([str(folder/'K文件处理台.exe'),'--check-archives','--report-dir',str(report)],cwd=folder,env=env,timeout=240)
assert result.returncode==0, result.returncode
record=json.loads((report/'archive-check.json').read_text('utf-8'))
assert record['status']=='passed' and len(record['checks'])==18
print('Frozen relocated archive checks: PASS (18 groups, Chinese/space paths, minimal PATH).')
report=root/'build/extra-portable'
result=subprocess.run([str(folder/'K文件处理台.exe'),'--check-extra','--report-dir',str(report)],cwd=folder,env=env,timeout=240)
assert result.returncode==0,result.returncode
record=json.loads((report/'extra-check.json').read_text('utf-8'))
assert record['status']=='passed' and len(record['checks'])==28
print('Frozen relocated extended conversions: PASS (28 directions).')
