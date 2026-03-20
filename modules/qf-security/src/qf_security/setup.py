#!/usr/bin/env python3
"""
QuantForge Security Setup Tool - 安全设置工具
用于初始化安全系统、加密配置文件等

用法:
    python -m qf_security.setup init              # 初始化安全系统
    python -m qf_security.setup encrypt-config    # 加密配置文件
    python -m qf_security.setup rotate-key        # 轮换密钥
    python -m qf_security.setup verify            # 验证安全设置
"""

import os
import sys
import json
import argparse
import getpass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from qf_security import (
    initialize_security,
    generate_master_key,
    save_master_key,
    get_master_key,
    SecureConfig,
    FernetEncryption,
    rotate_key,
)
from qf_security.exceptions import SecurityError


def print_banner():
    """打印欢迎信息"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║            QuantForge Security Setup Tool                    ║
║                    安全系统设置工具                           ║
╚══════════════════════════════════════════════════════════════╝
""")


def cmd_init(args):
    """初始化安全系统命令"""
    print("🔐 Initializing QuantForge Security System...")
    print()
    
    # 检查是否已有主密钥
    existing_key = get_master_key()
    if existing_key and not args.force:
        print("⚠️  Master key already exists.")
        response = input("   Do you want to overwrite? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    
    # 选择初始化方式
    print("Choose initialization method:")
    print("  1. Generate random master key (recommended)")
    print("  2. Derive from password")
    print()
    
    choice = input("Enter choice (1/2): ").strip()
    
    if choice == "1":
        master_key = generate_master_key()
        save_master_key(master_key)
        print()
        print("✅ Master key generated and saved.")
        print()
        print("⚠️  IMPORTANT: Please backup this key in a secure location!")
        print(f"   Key: {master_key}")
        
    elif choice == "2":
        password = getpass.getpass("Enter password: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("❌ Passwords do not match!")
            return
        
        if len(password) < 12:
            print("⚠️  Warning: Password should be at least 12 characters.")
            response = input("Continue anyway? (yes/no): ")
            if response.lower() != "yes":
                return
        
        master_key = initialize_security(password=password)
        print()
        print("✅ Security system initialized with password-derived key.")
        
    else:
        print("❌ Invalid choice.")
        return
    
    print()
    print("📍 Key location:")
    print(f"   {Path.home() / '.quantforge' / '.master_key'}")
    print()
    print("Next steps:")
    print("  1. Copy config/config.example.yaml to config/config.yaml")
    print("  2. Fill in your actual API keys and passwords")
    print("  3. Run: python -m qf_security.setup encrypt-config")


def cmd_encrypt_config(args):
    """加密配置文件命令"""
    print("🔒 Encrypting configuration file...")
    print()
    
    # 检查主密钥
    master_key = get_master_key()
    if not master_key:
        print("❌ Master key not found. Please run 'init' first.")
        return
    
    # 确定输入输出路径
    input_path = Path(args.input) if args.input else Path("config/config.yaml")
    output_path = Path(args.output) if args.output else Path("config/config.encrypted.json")
    
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print()
        print("Please create a config file first:")
        print(f"  cp config/config.example.yaml {input_path}")
        return
    
    # 读取配置
    try:
        import yaml
        with open(input_path) as f:
            config = yaml.safe_load(f)
    except ImportError:
        print("❌ PyYAML not installed. Trying JSON...")
        with open(input_path) as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read config: {e}")
        return
    
    # 加密配置
    try:
        secure_config = SecureConfig()
        encrypted = secure_config.encrypt_config_values(config)
        
        # 保存
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(encrypted, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Configuration encrypted and saved to: {output_path}")
        print()
        print("⚠️  IMPORTANT:")
        print("  - Keep the original config file secure or delete it")
        print("  - Do not commit the encrypted config to version control")
        print("  - Back up your master key!")
        
        # 显示加密了哪些字段
        encrypted_fields = []
        def find_encrypted(data, prefix=""):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    find_encrypted(value, full_key)
                elif isinstance(value, str) and value.startswith("ENC:"):
                    encrypted_fields.append(full_key)
        
        find_encrypted(encrypted)
        
        if encrypted_fields:
            print()
            print("🔐 Encrypted fields:")
            for field in encrypted_fields:
                print(f"   - {field}")
                
    except SecurityError as e:
        print(f"❌ Encryption failed: {e}")
        return


def cmd_rotate_key(args):
    """轮换密钥命令"""
    print("🔄 Rotating encryption key...")
    print()
    
    old_key = get_master_key()
    if not old_key:
        print("❌ Current master key not found.")
        return
    
    config_path = Path(args.config) if args.config else Path("config/config.encrypted.json")
    
    if not config_path.exists():
        print(f"❌ Encrypted config not found: {config_path}")
        return
    
    # 生成新密钥
    new_key = generate_master_key()
    
    try:
        rotated_key = rotate_key(old_key, new_key, config_path)
        save_master_key(rotated_key)
        
        print("✅ Key rotation completed successfully!")
        print()
        print("⚠️  New master key:")
        print(f"   {rotated_key}")
        print()
        print("Please backup this key in a secure location!")
        
    except SecurityError as e:
        print(f"❌ Key rotation failed: {e}")
        return


def cmd_verify(args):
    """验证安全设置命令"""
    print("🔍 Verifying QuantForge Security Setup...")
    print()
    
    checks = []
    
    # 检查主密钥
    master_key = get_master_key()
    checks.append(("Master key exists", master_key is not None))
    
    if master_key:
        checks.append(("Master key format valid", len(master_key) == 44))
    
    # 检查密钥文件权限
    key_file = Path.home() / ".quantforge" / ".master_key"
    if key_file.exists():
        import stat
        mode = key_file.stat().st_mode
        secure_permissions = (
            (mode & stat.S_IRUSR) and  # 所有者可读
            (mode & stat.S_IWUSR) and  # 所有者可写
            not (mode & stat.S_IRGRP) and  # 组不可读
            not (mode & stat.S_IROTH)      # 其他不可读
        )
        checks.append(("Key file permissions secure", secure_permissions))
    else:
        checks.append(("Key file exists", False))
    
    # 检查加密配置
    encrypted_config = Path("config/config.encrypted.json")
    checks.append(("Encrypted config exists", encrypted_config.exists()))
    
    # 检查环境变量
    checks.append(("QUANTFORGE_MASTER_KEY env var set", "QUANTFORGE_MASTER_KEY" in os.environ))
    
    # 打印结果
    print("Security Check Results:")
    print()
    
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
    
    passed_count = sum(1 for _, passed in checks if passed)
    total_count = len(checks)
    
    print()
    print(f"Score: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("🎉 All security checks passed!")
    elif passed_count >= total_count * 0.7:
        print("⚠️  Some security checks failed. Please review.")
    else:
        print("❌ Many security checks failed. Please run 'init' first.")


def cmd_decrypt(args):
    """解密配置查看命令"""
    print("🔓 Decrypting configuration...")
    print()
    
    master_key = get_master_key()
    if not master_key:
        print("❌ Master key not found.")
        return
    
    config_path = Path(args.config) if args.config else Path("config/config.encrypted.json")
    
    if not config_path.exists():
        print(f"❌ Encrypted config not found: {config_path}")
        return
    
    try:
        secure_config = SecureConfig()
        config = secure_config.load_encrypted_config(config_path)
        
        print(json.dumps(config, indent=2, ensure_ascii=False))
        
    except SecurityError as e:
        print(f"❌ Decryption failed: {e}")
        return


def main():
    parser = argparse.ArgumentParser(
        description="QuantForge Security Setup Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s init                    # Initialize security system
  %(prog)s encrypt-config          # Encrypt configuration
  %(prog)s verify                  # Verify security setup
  %(prog)s rotate-key              # Rotate encryption key
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # init command
    init_parser = subparsers.add_parser("init", help="Initialize security system")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing key")
    
    # encrypt-config command
    encrypt_parser = subparsers.add_parser("encrypt-config", help="Encrypt configuration file")
    encrypt_parser.add_argument("-i", "--input", help="Input config file (default: config/config.yaml)")
    encrypt_parser.add_argument("-o", "--output", help="Output encrypted file (default: config/config.encrypted.json)")
    
    # rotate-key command
    rotate_parser = subparsers.add_parser("rotate-key", help="Rotate encryption key")
    rotate_parser.add_argument("-c", "--config", help="Encrypted config file")
    
    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify security setup")
    
    # decrypt command
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt and view configuration")
    decrypt_parser.add_argument("-c", "--config", help="Encrypted config file")
    
    args = parser.parse_args()
    
    if not args.command:
        print_banner()
        parser.print_help()
        return
    
    # 执行命令
    commands = {
        "init": cmd_init,
        "encrypt-config": cmd_encrypt_config,
        "rotate-key": cmd_rotate_key,
        "verify": cmd_verify,
        "decrypt": cmd_decrypt,
    }
    
    if args.command in commands:
        print_banner()
        commands[args.command](args)
    else:
        print(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
