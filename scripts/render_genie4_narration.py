#!/usr/bin/env python3
"""Render verified VOICEVOX dialogue to per-line WAV and a 57s narration track.
Do not mark the resulting files as a finished video.
"""
import json
import pathlib
import sys
import wave
import array
import urllib.parse
import urllib.request
import time

BASE="http://127.0.0.1:50021"
SPEAKERS={"momokage":"†聖騎士 紅桜†","momonosuke":"猫使ビィ"}
def req(path,method="GET",body=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    r=urllib.request.Request(BASE+path,data=data,method=method,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=120) as response:return response.read()
def main():
    source=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    plan=json.loads(source.read_text(encoding="utf-8"))
    report={"production_date":plan["date"],"passed":False,"items":[],"errors":[]}
    try:
        for _ in range(90):
            try: speakers=json.loads(req("/speakers"));break
            except Exception:time.sleep(1)
        else:raise RuntimeError("VOICEVOX /speakers unavailable")
        ids={}
        for key,name in SPEAKERS.items():
            matches=[s for s in speakers if s["name"]==name]
            if len(matches)!=1:raise RuntimeError("Missing or ambiguous voice: "+name)
            styles=matches[0]["styles"]
            normal=next((s for s in styles if s["name"] in ("ノーマル","通常")),styles[0])
            ids[key]=normal["id"]
        report["speaker_ids"]=ids
        sample_rate=24000
        total_samples=int(plan["duration_seconds"]*sample_rate)
        track=array.array("i",[0])*total_samples
        for i,item in enumerate(plan["lines"]):
            sid=ids[item["speaker"]]
            q=urllib.parse.urlencode({"text":item["text"],"speaker":sid})
            query=json.loads(req("/audio_query?"+q,method="POST"))
            query["outputSamplingRate"]=sample_rate
            query["outputStereo"]=False
            wav=req("/synthesis?speaker="+str(sid),method="POST",body=query)
            filename=out/f"line_{i+1:02d}_{item['speaker']}.wav"
            filename.write_bytes(wav)
            with wave.open(str(filename),"rb") as f:
                if f.getframerate()!=sample_rate or f.getnchannels()!=1 or f.getsampwidth()!=2:
                    raise RuntimeError("Unexpected WAV format at line "+str(i+1))
                samples=array.array("h");samples.frombytes(f.readframes(f.getnframes()))
            start=int(item["start"]*sample_rate)
            end=int(item["end"]*sample_rate)
            if len(samples)>end-start:
                report["errors"].append(f"Line {i+1} exceeds allotted slot by {(len(samples)-(end-start))/sample_rate:.2f}s")
            if start+len(samples)>total_samples:report["errors"].append(f"Line {i+1} exceeds total duration")
            for k,v in enumerate(samples):
                idx=start+k
                if idx>=total_samples:break
                track[idx]+=v
            report["items"].append({"line":i+1,"speaker":item["speaker"],"speaker_id":sid,"text":item["text"],"start":item["start"],"end":item["end"],"speech_duration_seconds":round(len(samples)/sample_rate,3),"wav":filename.name})
        with wave.open(str(out/"narration_57s.wav"),"wb") as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(sample_rate)
            pcm=array.array("h",(max(-32768,min(32767,x)) for x in track))
            f.writeframes(pcm.tobytes())
        report["passed"]=not report["errors"]
    except Exception as e:
        report["errors"].append(str(e))
    (out/"narration_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["passed"] else 1
if __name__=="__main__":sys.exit(main())
