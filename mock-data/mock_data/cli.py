from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from .config import load_config
from .exporters import export, load_json_directory
from .generator import Generator
from .validators import validate


def report(data, config):
    result=validate(data,config["reference_date"])
    result={"seed":config["seed"],"reference_date":config["reference_date"],
      "generated_at":datetime.now(timezone(timedelta(hours=7))).isoformat(),**result}
    return result


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Sinh và kiểm tra mock data HeartCare AI")
    sub=parser.add_subparsers(dest="command",required=True)
    gen=sub.add_parser("generate",help="Sinh dataset"); gen.add_argument("--config",default="config/demo.yaml")
    gen.add_argument("--profile",choices=["demo","integration","load-test"]); gen.add_argument("--seed",type=int)
    gen.add_argument("--reference-date"); gen.add_argument("--format",action="append",choices=["json","jsonl","csv"])
    gen.add_argument("--output"); gen.add_argument("--count",action="append",default=[],metavar="TABLE=N")
    val=sub.add_parser("validate",help="Kiểm tra thư mục JSON"); val.add_argument("--input",required=True); val.add_argument("--reference-date",default="2026-07-17")
    args=parser.parse_args(argv)
    try:
        if args.command=="validate":
            data=load_json_directory(Path(args.input)); cfg={"seed":"unknown","reference_date":args.reference_date}; result=report(data,cfg)
            print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result["business_rules"]["passed"] else 1
        config_path=Path(args.config)
        if args.profile and args.config=="config/demo.yaml": config_path=Path("config")/f"{args.profile}.yaml"
        config=load_config(config_path)
        if args.seed is not None: config["seed"]=args.seed
        if args.reference_date: config["reference_date"]=args.reference_date
        for item in args.count:
            key,value=item.split("=",1); config["counts"][key]=int(value)
        formats=args.format or config["output"]["formats"]; out=Path(args.output or config["output"]["directory"])
        data=Generator(config).build(); result=report(data,config)
        export(data,out,formats,bool(config["output"].get("pretty_json")))
        (out/"validation-report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Seed: {config['seed']} | reference_date: {config['reference_date']} | collections: {len(data)}")
        for name,count in result["record_counts"].items(): print(f"{name}: {count}")
        print("Validation:","PASSED" if result["business_rules"]["passed"] else "FAILED")
        return 0 if result["business_rules"]["passed"] else 1
    except (ValueError,KeyError,OSError) as exc:
        print(f"Lỗi: {exc}",file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
