from pathlib import Path
import threading,zipfile,subprocess
import pytest
import archive_bridge


@pytest.fixture(autouse=True)
def isolated_data(tmp_path,monkeypatch):
    monkeypatch.setattr(archive_bridge,'DATA_ROOT',tmp_path/'engine-data')


def make_archive(folder,ext,password=None,aes=False,header=False):
    recovery,_,_=archive_bridge.initialize()
    folder.mkdir(parents=True,exist_ok=True); source=folder/'known.txt'; source.write_text('Known synthetic test data 123 中文','utf-8')
    path=folder/('fixture.'+ext); args=[str(recovery.find_7zip()),'a','-t'+ext]
    if password:args+=['-p'+password]
    if ext=='zip' and password:args+=['-mem=AES256' if aes else '-mem=ZipCrypto']
    if ext=='7z' and header:args+=['-mhe=on']
    result=subprocess.run([*args,str(path),str(source)],capture_output=True,creationflags=0x08000000)
    assert result.returncode==0
    return path


def run(path,output,request=None):
    return archive_bridge.recover_archive(path,request or {},False,True,output,threading.Event(),lambda *v:None,lambda *v:None)


def test_plain_extract_no_overwrite(tmp_path):
    path=make_archive(tmp_path/'source','zip'); before=path.read_bytes()
    item=archive_bridge.inspect_archive(path,threading.Event()); assert not item['encrypted'] and item['managed'] is False
    one=run(path,tmp_path/'out'); two=run(path,tmp_path/'out')
    assert one['destination']!=two['destination'] and path.read_bytes()==before
    assert (one['destination']/'known.txt').read_text('utf-8').startswith('Known')


@pytest.mark.parametrize('ext,aes,header',[('zip',False,False),('zip',True,False),('7z',False,True),('rar',False,False)])
def test_password_recovery(tmp_path,ext,aes,header):
    if ext=='rar':
        path=Path(__file__).parent/'fixtures/archive/fixture.rar'; password='portable-test-42!'
    else:
        password='KDemo123!'; path=make_archive(tmp_path/'source',ext,password,aes,header)
    assert archive_bridge.inspect_archive(path,threading.Event())['encrypted']
    result=run(path,tmp_path/'out',{'kind':'manual','lines':('wrong',password),'dictionary':None,'mask':''})
    assert result['found'] and result['password']==password and result['destination'].is_dir()


def test_unknown_length_mask(tmp_path):
    path=make_archive(tmp_path/'source','zip','abc7')
    result=run(path,tmp_path/'out',{'kind':'manual','lines':(),'dictionary':None,'mask':'abc',
        'mask_length_range':{'minimum':3,'maximum':4,'padding':'?d','anchor':'start'}})
    assert result['password']=='abc7'


def test_charset_and_dictionary(tmp_path):
    path=make_archive(tmp_path/'source','zip','7')
    result=run(path,tmp_path/'out',{'kind':'charset','alphabet':'0123456789','max_length':1})
    assert result['password']=='7'
    dictionary=tmp_path/'words.txt'; dictionary.write_text('no\n7\n','utf-16')
    result=run(path,tmp_path/'out',{'kind':'manual','lines':(),'dictionary':str(dictionary),'mask':''})
    assert result['password']=='7'


def test_stop_and_unsafe_entries(tmp_path):
    path=make_archive(tmp_path/'source','zip','abc7')
    recovery,_,_=archive_bridge.initialize(); stop=threading.Event(); stop.set()
    with pytest.raises(recovery.Cancelled):archive_bridge.recover_archive(path,{},True,True,tmp_path/'out',stop,lambda *v:None,lambda *v:None)
    bad=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../escape.txt','must never write outside')
    with pytest.raises(recovery.RecoveryError):run(bad,tmp_path/'out')
    assert not (tmp_path/'escape.txt').exists()


def test_combination_and_mask_contract():
    recovery,_,masks=archive_bridge.initialize()
    alphabet,length=recovery.combination_alphabet(['lowercase','digits'],2)
    assert 'a' in alphabet and '0' in alphabet and length==2
    assert masks.count(masks.masks('abc',3,4,'?d','start'))==11
