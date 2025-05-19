import os
import requests
import getpass

# 服务端 API 的基础 URL
SERVER_BASE_URL = "http://10.129.244.236:5001/api/config"

# 本地保存配置文件的目录 (可以根据你的项目结构调整)
CWD = os.path.dirname(os.path.abspath(__file__))

# 需要下载的配置文件信息
CONFIG_FILES_TO_DOWNLOAD = [
    {"server_endpoint": "env", "local_filename": ".env", "local_config_dir": "game"},
    {
        "server_endpoint": "yaml",
        "local_filename": "config.yaml",
        "local_config_dir": "config",
    },
]

DOWNLOAD_PASSWORD = "Tuavalon"


def verify_password() -> bool:
    """
    验证用户输入的密码。
    """
    print("需要密码以继续下载配置文件。")
    user_input = getpass.getpass("请输入密码：")
    if user_input == DOWNLOAD_PASSWORD:
        print("密码验证成功。")
        return True
    else:
        print("密码错误，拒绝访问配置文件。")
        return False


def download_config_file(endpoint: str, local_filepath: str) -> bool:
    """
    从服务端下载指定的配置文件并保存到本地。

    Args:
        endpoint (str): 服务端提供配置文件的端点名称 (例如 'env' 或 'yaml')。
        local_filepath (str): 本地保存文件的完整路径。

    Returns:
        bool: 如果下载和保存成功则返回 True, 否则返回 False。
    """
    url = f"{SERVER_BASE_URL}/{endpoint}"
    try:
        print(f"正在从 {url} 下载配置文件...")
        response = requests.get(url, timeout=10)  # 设置10秒超时
        response.raise_for_status()  # 如果请求失败 (状态码 4xx 或 5xx), 则抛出 HTTPError

        # 确保本地目录存在
        os.makedirs(os.path.dirname(local_filepath), exist_ok=True)

        with open(local_filepath, "wb") as f:  # 以二进制写入，保持原始编码
            f.write(response.content)
        print(f"配置文件已成功下载并保存到: {local_filepath}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"下载配置文件 {endpoint} 失败: {e}")
    except IOError as e:
        print(f"保存配置文件 {local_filepath} 失败: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")
    return False


def fetch_all_configs():
    """
    下载所有指定的配置文件。
    """
    print("开始同步配置文件...")
    all_successful = True
    # if not os.path.exists(LOCAL_CONFIG_DIR):
    #     os.makedirs(LOCAL_CONFIG_DIR)
    #     print(f"创建本地配置目录: {LOCAL_CONFIG_DIR}")

    for config_info in CONFIG_FILES_TO_DOWNLOAD:
        local_path = os.path.join(
            CWD, config_info["local_config_dir"], config_info["local_filename"]
        )
        if not download_config_file(config_info["server_endpoint"], local_path):
            all_successful = False
            print(f"警告: 未能同步 {config_info['local_filename']}")

    if all_successful:
        print("所有配置文件同步完成。")
    else:
        print("部分配置文件同步失败。应用程序可能使用旧的或默认配置。")
    return all_successful


if __name__ == "__main__":
    # 这是应用程序启动时应该执行的逻辑
    if verify_password():
        if fetch_all_configs():
            print("配置文件已准备就绪，应用程序可以继续启动。")
        else:
            print(
                "错误：未能获取所有必要的配置文件。应用程序可能无法正常启动或将使用默认/缓存配置。"
            )
            # 根据你的需求决定是否要在此处中止应用程序
    else:
        print("终止程序。")

    # ... 你的应用程序的其他启动代码 ...
    print("\n应用程序正在运行...")
