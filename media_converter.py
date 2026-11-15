"""Offline video remux/transcode, audio extraction and GIF clipping."""
from pathlib import Path
import math
import queue
import re
import subprocess
import threading
import time
from converter import ConversionError


def binary():
    import imageio_ffmpeg
    return str(next((Path(imageio_ffmpeg.__file__).parent/'binaries').glob('ffmpeg*.exe'),None) or imageio_ffmpeg.get_ffmpeg_exe())


def probe(path):
    try:
        result=subprocess.run([binary(),'-hide_banner','-nostdin','-protocol_whitelist','file,pipe','-i',str(path)],capture_output=True,timeout=30,creationflags=0x08000000)
    except subprocess.TimeoutExpired: raise ConversionError('读取音视频超时，请检查文件。') from None
    text=result.stderr.decode('utf-8','replace')
    header=re.search(r'Input #0, (.*?), from ',text)
    duration=re.search(r'Duration: (\d+):(\d+):([\d.]+)',text)
    if not header or not duration: raise ConversionError('无法读取音视频的容器或时长，文件可能损坏。')
    seconds=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
    videos=re.findall(r'Stream #0:(\d+).*?Video: ([^,\s]+)([^\r\n]*)',text)
    videos=[v for v in videos if 'attached pic' not in v[2]]
    audio=re.findall(r'Stream #0:(\d+).*?Audio: ([^,\s]+)',text)
    return {'duration':seconds,'has_video':bool(videos),'has_audio':bool(audio),'video_codec':videos[0][1] if videos else '',
            'audio_codec':audio[0][1] if audio else '', 'video_index':int(videos[0][0]) if videos else None,
            'audio_index':int(audio[0][0]) if audio else None,'container':header[1]}


def validate_media(path,ext):
    info=probe(path)
    containers={'mp4':'mov','mov':'mov','m4a':'mov','mkv':'matroska','webm':'matroska','wav':'wav','flac':'flac','mp3':'mp3','aac':'aac'}
    if containers[ext] not in info['container'].split(','): raise ConversionError('音视频内容与扩展名不一致。')
    if ext in ('mp4','mov','mkv','webm') and not info['has_video']: raise ConversionError('此文件没有可转换的视频流。')
    if ext in ('wav','flac','mp3','m4a','aac') and not info['has_audio']: raise ConversionError('此文件没有可转换的音轨。')
    if not 0<info['duration']<=86400: raise ConversionError('音视频时长须为正数且不超过 24 小时。')
    return info


def encode(source,output,args,duration,progress):
    command=[binary(),'-hide_banner','-loglevel','error','-nostdin','-y','-protocol_whitelist','file,pipe','-i',str(source),*args,
             '-progress','pipe:1','-nostats',str(output)]
    lines=queue.Queue()
    with (output.parent/'media-errors.txt').open('wb') as errors:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,stdin=subprocess.DEVNULL,text=True,creationflags=0x08000000)
        def reader():
            for line in process.stdout: lines.put(line.strip())
            lines.put(None)
        thread=threading.Thread(target=reader,daemon=True); thread.start(); deadline=time.monotonic()+1800
        try:
            while True:
                if time.monotonic()>deadline: raise ConversionError('音视频处理超过 30 分钟，请截短或降低分辨率后重试。')
                try: line=lines.get(timeout=.25)
                except queue.Empty: continue
                if line is None: break
                if line.startswith('out_time_us='):
                    try: value=12+int(82*min(1,max(0,int(line.split('=')[1]))/max(1,duration*1_000_000)))
                    except ValueError: continue
                    progress(value,'正在处理音视频流')
            return process.wait(timeout=10)==0
        finally:
            if process.poll() is None: process.kill(); process.wait()
            thread.join(timeout=2); process.stdout.close()


def convert_media(source,ext,target,directory,options,progress):
    info=validate_media(source,ext); output=directory/('result.'+target); notes=[]; duration=info['duration']
    audio=target in ('m4a','aac','mp3','wav','flac')
    if audio:
        if not info['has_audio']: raise ConversionError('文件没有音轨，无法提取音频。')
        mapping=['-map',f'0:{info["audio_index"]}','-vn']
        codec={'m4a':['-c:a','aac','-b:a','192k','-movflags','+faststart'], 'aac':['-c:a','aac','-b:a','192k','-f','adts'],
               'mp3':['-c:a','libmp3lame','-b:a','192k'],'wav':['-c:a','pcm_s16le'],'flac':['-c:a','flac']}[target]
        args=mapping+codec
        notes.append('使用第一条音轨；输出 WAV 采用 16 位 PCM。MP3 / AAC 为有损编码，不会恢复源文件已丢失的信息。')
    elif target=='gif':
        try: start=float(options.get('clip_start',0)); length=float(options.get('clip_duration',5)); fps=int(options.get('gif_fps',12)); width=int(options.get('gif_width',480))
        except (TypeError,ValueError): raise ConversionError('动图参数必须为有效数字。') from None
        if not all(math.isfinite(v) for v in (start,length)) or start<0 or start>=duration or not 0<length<=30 or not 1<=fps<=30 or not 64<=width<=1280:
            raise ConversionError('动图起点需在视频内，时长 0–30 秒，帧率 1–30，宽度 64–1280。')
        duration=min(length,duration-start)
        filters=f'[0:{info["video_index"]}]fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse[out]'
        args=['-ss',str(start),'-t',str(duration),'-map','[out]','-an','-filter_complex',filters,'-loop','0']
        notes.append(f'已从 {start:g} 秒开始截取 {duration:g} 秒；GIF 不保存声音。')
    else:
        mapping=['-map',f'0:{info["video_index"]}']+(['-map',f'0:{info["audio_index"]}'] if info['has_audio'] else [])
        # Try exact stream copy where the destination container accepts it.
        compatible=target=='mkv' or (target in ('mp4','mov') and info['video_codec'] in ('h264','hevc','av1','mpeg4') and (not info['has_audio'] or info['audio_codec'] in ('aac','mp3','alac')))
        if compatible:
            progress(15,'正在无损换封装')
            if encode(source,output,mapping+['-c','copy']+(['-movflags','+faststart'] if target in ('mp4','mov') else []),duration,progress):
                progress(98,'正在保存音视频'); return output,['已直接复制首条视频和音轨，无重编码；字幕、附件及其他轨道未导出。']
            output.unlink(missing_ok=True)
        codec=['-c:v','libvpx-vp9','-crf','32','-b:v','0','-c:a','libopus'] if target=='webm' else ['-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2']
        args=mapping+codec+(['-movflags','+faststart'] if target in ('mp4','mov') else [])
        notes.append('已转码首条视频和音轨；字幕、附件及其他轨道未导出，视频编码可能改变画质。')
    if not encode(source,output,args,duration,progress): raise ConversionError('音视频编码失败，源编码或所选容器可能不兼容。')
    if not output.is_file() or not output.stat().st_size: raise ConversionError('未生成有效的音视频文件。')
    progress(98,'正在保存音视频'); return output,notes
