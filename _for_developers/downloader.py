import paramiko
import os
import tarfile
import tempfile
import sys
from scp import SCPClient
from pathlib import Path

# 动态计算基础目录
# 配置信息
SERVER_IP = "10.129.244.236"
USERNAME = "rocky"
PASSWORD = "PKU2025dsa"
SCRIPT_DIR = Path(__file__).parent.absolute()
LOCAL_BASE_DIR = SCRIPT_DIR.parent / "data"  # 上级目录的data文件夹


def validate_local_dir():
    """确保本地存储目录存在且有写入权限"""
    try:
        LOCAL_BASE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = LOCAL_BASE_DIR / ".permission_test"
        test_file.touch()
        test_file.unlink()
    except PermissionError:
        print(f"错误：无法写入目录 {LOCAL_BASE_DIR}")
        print("请尝试以下解决方案：")
        print("1. 以管理员身份运行脚本")
        print("2. 手动创建目录并赋予写权限")
        sys.exit(1)
    except Exception as e:
        print(f"目录验证失败: {str(e)}")
        sys.exit(1)


def create_ssh_connection():
    """创建SSH连接并返回客户端对象"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(SERVER_IP, username=USERNAME, password=PASSWORD, timeout=10)
        return ssh
    except Exception as e:
        print(f"连接失败: {str(e)}")
        return None


def get_remote_home(ssh):
    """获取远程用户的实际home目录"""
    _, stdout, _ = ssh.exec_command("echo ~")
    return stdout.read().decode().strip()


def main():
    # 初始化时验证目录
    validate_local_dir()
    # 初始化SSH连接
    ssh = create_ssh_connection()
    if not ssh:
        return

    # 获取远程用户真实home路径
    home_dir = get_remote_home(ssh)
    sftp = ssh.open_sftp()
    scp = SCPClient(ssh.get_transport())

    try:
        while True:
            user_input = input("请输入gameid（输入:q退出）: ").strip()

            if user_input == ":q":
                print("正在退出...")
                break

            gameid = user_input
            remote_dir = f"{home_dir}/pkudsa.avalon/data/{gameid}"
            local_dir = LOCAL_BASE_DIR / gameid  # 使用Path对象处理路径

            try:
                # 验证远程目录存在
                sftp.stat(remote_dir)
            except FileNotFoundError:
                print(f"✖ 服务器不存在该gameid: {gameid}")
                continue

            # 创建临时文件路径（兼容Windows）
            with tempfile.TemporaryDirectory() as tmp_dir:
                remote_temp = f"/tmp/{gameid}_transfer.tar.gz"
                local_temp = os.path.join(
                    tmp_dir, f"{gameid}_transfer.tar.gz"
                )  # 使用临时目录

            try:
                # 在服务器创建压缩包
                print("正在创建远程压缩包...")
                compress_cmd = f"tar -czf {remote_temp} -C {remote_dir} ."
                _, stdout, stderr = ssh.exec_command(compress_cmd)
                exit_status = stdout.channel.recv_exit_status()

                if exit_status != 0:
                    error = stderr.read().decode()
                    raise Exception(f"压缩失败: {error}")

                # 下载压缩包
                print("正在下载...")
                os.makedirs(tmp_dir, exist_ok=True)  # 确保临时目录存在
                scp.get(remote_temp, local_temp)

                # 创建本地目录并解压
                os.makedirs(local_dir, exist_ok=True)
                print("正在解压文件...")
                with tarfile.open(local_temp, "r:gz") as tar:

                    def safe_extract(member):
                        # 防止路径遍历攻击
                        member.path = os.path.normpath(member.path).lstrip(os.sep)
                        return member

                    tar.extractall(path=local_dir, filter="data")  # 安全解压

                print(f"✔ 成功下载到: {local_dir}")

            finally:
                # 清理临时文件
                if os.path.exists(local_temp):
                    os.remove(local_temp)
                ssh.exec_command(f"rm -f {remote_temp}")

    finally:
        # 关闭连接
        scp.close()
        sftp.close()
        ssh.close()
        print("连接已关闭")


if __name__ == "__main__":
    main()
