#!/usr/bin/env python3
"""
QuantForge 混沌测试和压力测试运行脚本
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def print_header(title):
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="QuantForge 测试运行器")
    parser.add_argument("test_type", choices=["chaos", "stress", "all"], 
                       help="测试类型: chaos (混沌测试), stress (压力测试), all (全部)")
    parser.add_argument("--target", default="http://localhost:8000", 
                       help="目标服务地址")
    parser.add_argument("--duration", type=int, default=3600,
                       help="测试持续时间(秒)")
    
    args = parser.parse_args()
    
    if args.test_type in ["chaos", "all"]:
        print_header("运行混沌测试")
        try:
            from tests.chaos.chaos_monkey import main as chaos_main
            # 设置环境变量
            os.environ["TARGET_SERVICES"] = "qf-data,qf-strategy,qf-execution"
            os.environ["RUN_DURATION"] = str(args.duration)
            asyncio.run(chaos_main())
        except Exception as e:
            print(f"混沌测试出错: {e}")
            import traceback
            traceback.print_exc()
    
    if args.test_type in ["stress", "all"]:
        print_header("运行压力测试")
        try:
            from tests.stress.stress_test import main as stress_main
            # 设置环境变量
            os.environ["TARGET_HOST"] = args.target
            asyncio.run(stress_main())
        except Exception as e:
            print(f"压力测试出错: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
