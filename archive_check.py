"""Portable acceptance checks using public passwords and synthetic archives only."""
from pathlib import Path
import json,subprocess,tempfile,threading,zipfile
import archive_bridge


def run_checks(report_directory):
    report=Path(report_directory).resolve(); report.mkdir(parents=True,exist_ok=True)
    archive_bridge.DATA_ROOT=report/'working/engine-data'
    recovery,_,masks=archive_bridge.initialize(); engine=recovery.find_7zip(); records=[]
    with tempfile.TemporaryDirectory(prefix='K 解压 portable ') as temporary:
        root=Path(temporary); note=root/'合成 test.txt'; note.write_text('Known synthetic content 123','utf-8')
        def create(ext,options):
            path=root/('sample '+str(len(records))+'.'+ext)
            result=subprocess.run([str(engine),'a','-t'+ext,*options,str(path),str(note)],capture_output=True,creationflags=0x08000000)
            assert result.returncode==0
            return path
        for label,ext,options,password in [('plain','zip',[],None),('ZipCrypto','zip',['-mem=ZipCrypto','-pKTest123!'],'KTest123!'),
               ('AES-256','zip',['-mem=AES256','-pKTest123!'],'KTest123!'),('7z-header','7z',['-mhe=on','-pKTest123!'],'KTest123!')]:
            path=create(ext,options); original=path.read_bytes(); backends=[]
            request={'kind':'manual','lines':('wrong',password),'dictionary':None,'mask':''} if password else {}
            info=archive_bridge.recover_archive(path,request,False,True,root/'outputs',threading.Event(),lambda *v:None,lambda *v:backends.append(' '.join(map(str,v))))
            assert info['found'] and info['password']==password and path.read_bytes()==original
            assert (info['destination']/note.name).read_text('utf-8')=='Known synthetic content 123'
            records.append({'case':label,'passed':True,'backend':backends}); print(label+': PASS',flush=True)
        fixture=Path(__file__).parent/'tests/fixtures/archive/fixture.rar'
        if not fixture.exists():fixture=archive_bridge.converter.HOME/'source/tests/fixtures/archive/fixture.rar'
        info=archive_bridge.recover_archive(fixture,{'kind':'manual','lines':('wrong','portable-test-42!'),'dictionary':None,'mask':''},False,True,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
        assert info['found'] and info['destination'].is_dir(); records.append({'case':'RAR','passed':True}); print('RAR: PASS',flush=True)
        bad=root/'unsafe.zip'
        with zipfile.ZipFile(bad,'w') as zipped:zipped.writestr('../escape.txt','never write outside')
        try:archive_bridge.recover_archive(bad,{},False,True,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
        except recovery.RecoveryError:pass
        else:raise AssertionError('Unsafe archive was extracted')
        assert not (root/'escape.txt').exists(); records.append({'case':'unsafe-path-rejected','passed':True})
        assert masks.count(masks.masks('abc',3,4,'?d','start'))==11
        records.append({'case':'mask-length-range','passed':True})
        # Exercise each public search strategy on synthetic, known passwords.
        for kind in ('quick','deep'):
            path=create('zip',['-mem=ZipCrypto','-ppassword'])
            info=archive_bridge.recover_archive(path,{'kind':kind},False,False,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
            assert info['password']=='password' and info['destination'] is None
            records.append({'case':kind+'-search','passed':True}); print(kind+' search: PASS',flush=True)
        digit=create('zip',['-mem=ZipCrypto','-p7'])
        dictionary=root/'synthetic-words.txt';dictionary.write_text('wrong\n7\n','utf-16')
        for label,request in [
            ('combination',{'kind':'combination','types':['digits'],'max_length':1}),
            ('charset',{'kind':'charset','alphabet':'0123456789','max_length':1}),
            ('dictionary',{'kind':'manual','lines':(),'dictionary':str(dictionary),'mask':''}),
        ]:
            info=archive_bridge.recover_archive(digit,request,False,False,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
            assert info['password']=='7'
            records.append({'case':label+'-search','passed':True}); print(label+' search: PASS',flush=True)
        path=create('zip',['-mem=ZipCrypto','-pabc7'])
        request={'kind':'manual','lines':(),'dictionary':None,'mask':'abc','mask_length_range':{'minimum':3,'maximum':4,'padding':'?d','anchor':'start'}}
        info=archive_bridge.recover_archive(path,request,False,False,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
        assert info['password']=='abc7'
        records.append({'case':'mask-length-search','passed':True})
        stop=threading.Event();stop.set()
        try:archive_bridge.recover_archive(path,request,True,False,root/'outputs',stop,lambda *v:None,lambda *v:None)
        except recovery.Cancelled:pass
        else:raise AssertionError('Cancelled search continued')
        records.append({'case':'search-cancel','passed':True})
        import tarfile,io
        for ext,mode in [('tar','w'),('tar.gz','w:gz'),('tar.xz','w:xz')]:
            path=root/('合成.'+ext)
            with tarfile.open(path,mode) as archive:archive.add(note,arcname='nested/known.txt')
            assert not archive_bridge.inspect_archive(path,threading.Event())['encrypted']
            info=archive_bridge.recover_archive(path,{},False,True,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
            assert (info['destination']/'nested/known.txt').read_text('utf-8')=='Known synthetic content 123'
            records.append({'case':ext,'passed':True})
        path=root/'unsafe.tar'
        with tarfile.open(path,'w') as archive:
            entry=tarfile.TarInfo('../outside.txt');entry.size=1;archive.addfile(entry,io.BytesIO(b'x'))
        try:archive_bridge.recover_archive(path,{},False,True,root/'outputs',threading.Event(),lambda *v:None,lambda *v:None)
        except archive_bridge.converter.ConversionError:pass
        else:raise AssertionError('Unsafe TAR was extracted')
        records.append({'case':'unsafe-tar-rejected','passed':True})
    result={'status':'passed','checks':records}
    (report/'archive-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print('Archive portable acceptance: '+str(len(records))+' checks passed.',flush=True)
    return result
