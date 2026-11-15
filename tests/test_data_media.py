from pathlib import Path
import csv,json,subprocess
import pytest
import yaml
from lxml import etree
from PIL import Image
import converter
from data_converter import load_data
from media_converter import binary,probe


@pytest.fixture(scope='session')
def samples_v07(tmp_path_factory):
    folder=tmp_path_factory.mktemp('data-media')
    data=[{'编号':'001','数量':12,'有效':True,'备注':None},{'编号':'002','数量':34,'有效':False,'备注':'中文'}]
    (folder/'sample.json').write_text(json.dumps(data,ensure_ascii=False),'utf-8')
    (folder/'sample.yaml').write_text(yaml.safe_dump(data,allow_unicode=True),'utf-8')
    (folder/'sample.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><items version="1"><item id="001">中文</item><item id="002">测试</item></items>','utf-8')
    (folder/'sample.csv').write_text('编号,数量\n001,12\n002,34\n','utf-8-sig')
    def ff(args):
        p=subprocess.run([binary(),'-hide_banner','-loglevel','error','-y',*args],capture_output=True,creationflags=0x08000000)
        assert p.returncode==0,p.stderr
    ff(['-f','lavfi','-i','testsrc2=size=160x120:rate=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(folder/'sample.mp4')])
    ff(['-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1.2','-c:a','pcm_s16le',str(folder/'sample.wav')])
    for ext,args in [('webm',['-c:v','libvpx-vp9','-c:a','libopus']),('mkv',['-c','copy']),('mov',['-c','copy'])]:
        ff(['-i',str(folder/'sample.mp4'),*args,str(folder/('sample.'+ext))])
    ff(['-i',str(folder/'sample.wav'),'-c:a','flac',str(folder/'sample.flac')])
    ff(['-i',str(folder/'sample.mp4'),'-an','-c:v','copy',str(folder/'silent.mp4')])
    return folder


from extended_check import NEW
NEW_EDGES=[(ext,t) for ext in converter.DATA_EXTENSIONS for t in converter.GRAPH[ext] if t!='xlsx' and t not in NEW.get(ext,[])]+[(ext,t) for ext in converter.MEDIA_EXTENSIONS for t in converter.GRAPH.get(ext,[]) if t not in NEW.get(ext,[])]


@pytest.mark.parametrize('ext,target',NEW_EDGES)
def test_new_edges(samples_v07,tmp_path,ext,target):
    source=samples_v07/('sample.'+ext); converter.validate(source,ext)
    events=[]; output,notes=converter.convert(source,target,tmp_path/'result',{'clip_duration':.6,'gif_width':160,'gif_fps':10},lambda p,m:events.append(p))
    assert output.stat().st_size>10 and events[-1]==98
    if target=='gif':
        with Image.open(output) as image: assert image.width==160 and image.n_frames>=4
    elif target in ('json','yaml','xml','csv'):
        result=load_data(output,target); assert result is not None
        if ext=='csv': assert result[0]['编号']=='001'
        if ext=='yaml': assert result[0]['数量']==12 and result[0]['有效'] is True
        if ext=='xml': assert result['items']['@version']=='1' and len(result['items']['item'])==2
    else:
        info=probe(output); assert .9<info['duration']<1.6
        if target in ('m4a','aac','wav','mp3','flac'): assert info['has_audio'] and not info['has_video']
        else: assert info['has_video'] and info['has_audio']


def test_mappings(tmp_path):
    source=tmp_path/'x.json'; source.write_text('{"data":{"items":[{"id":"001","extra":{"a":1}}]}}','utf-8')
    output,_=converter.convert(source,'csv',tmp_path/'csv',{'records_path':'data.items'},lambda *a:None)
    with output.open(encoding='utf-8-sig') as f: row=next(csv.DictReader(f))
    assert row['id']=='001' and json.loads(row['extra'])=={'a':1}
    with pytest.raises(converter.ConversionError): converter.convert(source,'csv',tmp_path/'reject',{'records_path':'data.items','nested_csv':'reject'},lambda *a:None)
    source.write_text('{"root":{"@id":"001","item":["甲","乙"],"empty":null}}','utf-8')
    output,_=converter.convert(source,'xml',tmp_path/'xml',{},lambda *a:None)
    result=load_data(output,'xml'); assert result['root']['@id']=='001' and result['root']['item']==['甲','乙']
    output,_=converter.convert(output,'json',tmp_path/'json',{'xml_mode':'elements'},lambda *a:None)
    assert '@id' not in json.loads(output.read_text('utf-8'))['root']


@pytest.mark.parametrize('ext,content',[
 ('json','{"a":1,"a":2}'),('json','{"v":NaN}'),('yaml','a: 1\na: 2'),('yaml','a: &a [1]\nb: *a'),
 ('yaml','!!python/object/apply:os.system [echo bad]'),('yaml','1: hi'),('yaml','v: .nan'),
 ('xml','<!DOCTYPE a [<!ENTITY x SYSTEM "file:///secret">]><a>&x;</a>'),
 ('xml','<a>hello<b>x</b>world</a>'),('csv','id,id\n1,2'),('csv','a,b\n1,2,3')])
def test_invalid_data(tmp_path,ext,content):
    source=tmp_path/('invalid.'+ext); source.write_text(content,'utf-8')
    with pytest.raises(converter.ConversionError): converter.validate(source,ext)


def test_yaml_json_types(tmp_path):
    path=tmp_path/'types.yaml'; path.write_text('yes: yes\non: on\nid: 001\ndate: 2026-11-14\nflag: true\ncount: 12','utf-8')
    value=load_data(path,'yaml'); assert value=={'yes':'yes','on':'on','id':'001','date':'2026-11-14','flag':True,'count':12}


def test_silent_video_and_clip_errors(samples_v07,tmp_path):
    source=samples_v07/'silent.mp4'; info=converter.validate(source,'mp4')
    assert not info['has_audio'] and 'mp3' not in converter.targets_for('mp4',info)
    with pytest.raises(converter.ConversionError): converter.convert(source,'mp3',tmp_path/'audio',{},lambda *a:None)
    for options in [{'clip_start':10},{'clip_duration':31},{'gif_width':32}]:
        with pytest.raises(converter.ConversionError): converter.convert(source,'gif',tmp_path/'gif',options,lambda *a:None)


def test_remux_preserves_streams(samples_v07,tmp_path):
    source=samples_v07/'sample.mp4'
    output,notes=converter.convert(source,'mkv',tmp_path/'mkv',{},lambda *a:None)
    assert '无重编码' in notes[0]
    def streams(path):
        p=subprocess.run([binary(),'-v','error','-i',str(path),'-map','0','-c','copy','-f','streamhash','-'],capture_output=True,creationflags=0x08000000)
        assert p.returncode==0
        return p.stdout.splitlines()
    assert streams(source)==streams(output)
