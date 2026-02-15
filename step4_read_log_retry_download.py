<<<<<<< HEAD
import subprocess
import time
import os
import glob
import psutil
import socket
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys


def is_port_open(port, host='127.0.0.1'):
    """检查端口是否开放"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def check_edge_debug_port(pid):
    """检查指定PID的Edge进程是否启用了远程调试端口"""
    try:
        process = psutil.Process(pid)
        cmdline = ' '.join(process.cmdline())
        
        if '--remote-debugging-port=' in cmdline:
            for arg in process.cmdline():
                if arg.startswith('--remote-debugging-port='):
                    port = int(arg.split('=')[1])
                    return True, port
        return False, None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False, None


def find_edge_debug_port():
    """查找所有启用了远程调试的Edge进程"""
    debug_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'msedge.exe' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline:
                    for arg in cmdline:
                        if '--remote-debugging-port=' in str(arg):
                            port = int(arg.split('=')[1])
                            debug_processes.append((proc.info['pid'], port))
                            break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return debug_processes


def start_edge_with_debug(debugger_port=9222, user_data_dir=None, download_dir=None):
    """启动带远程调试的Edge浏览器"""
    edge_path = r"G:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    if not os.path.exists(edge_path):
        edge_path = r"G:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    if not os.path.exists(edge_path):
        print("错误: 未找到Edge浏览器")
        return None
    
    cmd = [
        edge_path,
        f"--remote-debugging-port={debugger_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions"
    ]
    
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")
    
    print(f"启动Edge浏览器 (调试端口: {debugger_port})...")
    subprocess.Popen(cmd)

    max_wait = 30
    wait_time = 0
    while wait_time < max_wait:
        time.sleep(1)
        wait_time += 1
        
        if is_port_open(debugger_port):
            print(f"✓ Edge浏览器已启动并监听端口 {debugger_port}")
            # 额外等待2秒确保调试接口完全初始化
            time.sleep(2)
            return debugger_port
            
        print(f"等待Edge浏览器启动... ({wait_time}/{max_wait}秒)")

    print(f"✗ 等待超时，Edge浏览器可能未正确启动")
    return None


def read_failed_urls(file_path):
    """读取失败的URL列表"""
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    urls = []
    for line in lines:
        line = line.strip()
        if line.startswith("下载失败: "):
            url = line.replace("下载失败: ", "").strip()
            urls.append(url)
        elif line.startswith("http"):
            urls.append(line)
    return urls


def log_result(log_file, message):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")


def connect_to_existing_edge(debugger_port=9222, download_dir=None, max_retries=5, retry_interval=2):
    """连接到已运行的Edge浏览器"""
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debugger_port}")
    
    # 配置下载行为
    if download_dir:
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,  # 自动下载PDF而不是在浏览器中打开
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        edge_options.add_experimental_option("prefs", prefs)
    
    for attempt in range(max_retries):
        try:
            driver = webdriver.Edge(options=edge_options)
            print(f"✓ 成功连接到端口 {debugger_port} 的Edge浏览器")
            
            # 设置下载行为（通过CDP）
            if download_dir:
                driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": download_dir
                })
            
            return driver
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"✗ 连接失败 (尝试 {attempt + 1}/{max_retries}), 错误: {str(e)[:100]}")
                print(f"  {retry_interval}秒后重试...")
                time.sleep(retry_interval)
            else:
                print(f"✗ 无法连接到端口 {debugger_port}")
                print(f"  错误详情: {str(e)}")
                print(f"  提示: 请确保Edge浏览器已启动并启用了远程调试端口 {debugger_port}")
                return None


def wait_for_pdf_load(driver, timeout=30):
    """等待PDF加载完成"""
    try:
        # 方法1: 检查PDF viewer是否加载完成
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # 方法2: 检查是否是PDF内容类型
        time.sleep(2)  # 给PDF渲染一些时间
        
        # 方法3: 尝试检测PDF插件或embed元素
        try:
            pdf_elements = driver.find_elements(By.TAG_NAME, "embed") + \
                          driver.find_elements(By.TAG_NAME, "object")
            if pdf_elements:
                print("  → 检测到PDF嵌入元素")
        except:
            pass
        
        return True
    except TimeoutException:
        print("  ✗ PDF加载超时")
        return False


def save_pdf_automatically(driver, save_dir, timeout=30):
    """自动保存PDF"""
    try:
        # 使用Ctrl+S快捷键触发保存
        from selenium.webdriver.common.action_chains import ActionChains
        
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
        
        print("  → 已发送保存命令 (Ctrl+S)")
        time.sleep(2)
        
        # 按Enter确认保存（如果弹出保存对话框）
        actions.send_keys(Keys.RETURN).perform()
        time.sleep(1)
        
        return True
    except Exception as e:
        print(f"  ✗ 自动保存失败: {str(e)[:100]}")
        return False


def check_download_complete(download_dir, files_before, timeout=60):
    """检查下载是否完成"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 检查是否有临时文件
        temp_files = glob.glob(os.path.join(download_dir, "*.crdownload")) + \
                     glob.glob(os.path.join(download_dir, "*.tmp"))
        
        if not temp_files:
            # 检查是否有新文件
            files_after = set(os.listdir(download_dir))
            new_files = files_after - files_before
            
            if new_files:
                # 确保文件不是0字节
                for new_file in new_files:
                    file_path = os.path.join(download_dir, new_file)
                    if os.path.getsize(file_path) > 0:
                        return True, new_files
            
        time.sleep(0.5)
    
    return False, set()


def is_driver_valid(driver):
    """检查driver是否仍然有效"""
    try:
        # 尝试获取当前窗口句柄，如果窗口已关闭会抛出异常
        driver.current_window_handle
        return True
    except:
        return False


def reconnect_driver(debugger_port, save_dir, max_retries=3):
    """重新连接到浏览器"""
    for attempt in range(max_retries):
        try:
            print(f"  → 尝试重新连接到浏览器 (尝试 {attempt + 1}/{max_retries})...")
            new_driver = connect_to_existing_edge(debugger_port, save_dir, max_retries=2)
            if new_driver and is_driver_valid(new_driver):
                print("  ✓ 重新连接成功")
                return new_driver
        except Exception as e:
            print(f"  ✗ 重新连接失败: {str(e)[:100]}")
        time.sleep(2)
    return None


def main():
    
    import psutil
    import sys
    def get_edge_pids():
        """
        获取所有 Microsoft Edge 进程的 PID
        :return: 包含所有 Edge 进程 PID 的列表
        """
        edge_pids = []
        # 遍历系统中所有正在运行的进程
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # 检查进程名称是否为 msedge.exe
                if proc.info['name'] == 'msedge.exe':
                    edge_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 忽略无法访问的进程
                continue
        return edge_pids

    # 获取并打印 Edge 的 PID
    TARGET_PID = get_edge_pids()
    print(f"找到的 Edge 进程 PID: {TARGET_PID}")

    # 如果你只需要获取第一个找到的 PID（通常是主进程），可以这样写：
    # 传入列表中的第一个元素（主进程 PID）
    # 使用 if 确保列表不为空，避免 IndexError
    if TARGET_PID:
        has_debug, port = check_edge_debug_port(TARGET_PID[0])
    else:
        print("错误：未找到 Edge 进程，无法检查调试端口。")
        # 根据你的逻辑处理这种情况，可能是退出或抛出异常
        sys.exit(1) 


    # 配置参数
    # TARGET_PID = 2104
    DIR = os.getcwd()
    print(f"当前目录: {DIR}")
    Py_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"当前python目录: {Py_DIR}")
    error_file = os.path.join(Py_DIR, "step3_download_errors.log")
    save_dir = os.path.join(Py_DIR, "step4_retry_downloads_from_failed")
    log_file = os.path.join(Py_DIR, "step4_retry_log_failed.txt")
    failed_log = os.path.join(Py_DIR, "step4_retry_failed.txt")
    
    batch_size = 10
    batch_delay = 10
    download_timeout = 60
    page_load_timeout = 60
    pdf_load_timeout = 60
    
    os.makedirs(save_dir, exist_ok=True)
    
    urls = read_failed_urls(error_file)
    if not urls:
        print("没有找到需要重试的URL")
        return
    
    print(f"找到 {len(urls)} 个失败链接")
    log_result(log_file, f"开始重试下载,共 {len(urls)} 个链接")
    
    print(f"\n检查PID={TARGET_PID[0]}的Edge进程...")
    has_debug, port = check_edge_debug_port(TARGET_PID[0])
    
    driver = None
    
    if has_debug:
        print(f"✓ 检测到PID={TARGET_PID}的Edge已启用远程调试 (端口: {port})")
        driver = connect_to_existing_edge(port, save_dir)
    else:
        print(f"✗ PID={TARGET_PID}的Edge未启用远程调试")
        
        debug_processes = find_edge_debug_port()
        if debug_processes:
            print(f"\n发现以下Edge进程已启用远程调试:")
            for pid, port in debug_processes:
                print(f"  - PID: {pid}, 端口: {port}")
            
            print(f"\n尝试连接到PID={debug_processes[0][0]}...")
            driver = connect_to_existing_edge(debug_processes[0][1], save_dir)
        
        if driver is None:
            common_ports = [9222, 9223, 9224]
            for test_port in common_ports:
                if is_port_open(test_port):
                    print(f"\n检测到端口 {test_port} 已开放，尝试连接...")
                    driver = connect_to_existing_edge(test_port, save_dir)
                    if driver:
                        break
        
        if driver is None:
            print("\n未找到可用的调试模式Edge浏览器")
            print("\n或者,让程序启动新的Edge浏览器? (y/n): ", end='')
            
            choice = input().strip().lower()
            if choice == 'y':
                # 创建临时用户数据目录
                temp_user_data = os.path.join(Py_DIR, "edge_debug_profile")
                port = start_edge_with_debug(9222, user_data_dir=temp_user_data, download_dir=save_dir)
                if port:
                    # 增加重试次数和重试间隔
                    driver = connect_to_existing_edge(port, save_dir, max_retries=10, retry_interval=3)
            
            if driver is None:
                print("无法建立连接,程序退出")
                return
    
    driver.set_page_load_timeout(page_load_timeout)
    
    try:
        total_success = 0
        total_failed = 0
        failed_urls = []
        
        for batch_num in range(0, len(urls), batch_size):
            batch_urls = urls[batch_num:batch_num + batch_size]
            batch_index = batch_num // batch_size + 1
            
            print(f"\n{'='*60}")
            print(f"处理第 {batch_index} 批 ({len(batch_urls)} 个链接)")
            print(f"{'='*60}")
            log_result(log_file, f"开始处理第 {batch_index} 批")
            
            for i, url in enumerate(batch_urls):
                global_index = batch_num + i + 1
                print(f"\n[{global_index}/{len(urls)}] 处理: {url}")
                
                files_before = set(os.listdir(save_dir))
                
                try:
                    driver.get(url)
                    print("  → 页面加载成功")

                    if 'academic.oup.com' in url:
                        time.sleep(10)
                        print("  → 检测到academic.oup.com，已等待10秒完成安全验证")

                    # 等待PDF加载完成
                    print(f"  → 等待PDF加载完成 (最多 {pdf_load_timeout} 秒)...")
                    if wait_for_pdf_load(driver, pdf_load_timeout):
                        print("  ✓ PDF加载完成")
                        
                        # 自动保存PDF
                        save_pdf_automatically(driver, save_dir)
                        
                        # 检查下载是否完成
                        print(f"  → 等待下载完成 (最多 {download_timeout} 秒)...")
                        success, new_files = check_download_complete(save_dir, files_before, download_timeout)
                        
                        if success:
                            total_success += 1
                            print(f"  ✓ 下载成功: {', '.join(new_files)}")
                            log_result(log_file, f"成功: {url} | 文件: {', '.join(new_files)}")
                        else:
                            total_failed += 1
                            failed_urls.append(url)
                            print(f"  ✗ 下载超时或未检测到新文件")
                            log_result(log_file, f"失败: {url} | 原因: 下载超时或未检测到文件")
                    else:
                        total_failed += 1
                        failed_urls.append(url)
                        print(f"  ✗ PDF加载超时")
                        log_result(log_file, f"失败: {url} | 原因: PDF加载超时")
                        
                except TimeoutException:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ 页面加载超时")
                    log_result(log_file, f"失败: {url} | 原因: 页面加载超时")
                    
                except WebDriverException as e:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ WebDriver错误: {str(e)[:100]}")
                    log_result(log_file, f"失败: {url} | 原因: {str(e)[:200]}")
                    
                except Exception as e:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ 未知错误: {str(e)[:100]}")
                    log_result(log_file, f"失败: {url} | 原因: {str(e)[:200]}")
                
                time.sleep(2)
            
            if batch_num + batch_size < len(urls):
                print(f"\n⏸ 等待 {batch_delay} 秒后继续下一批...")
                time.sleep(batch_delay)
        
        print(f"\n{'='*60}")
        summary = f"完成! 成功: {total_success}, 失败: {total_failed}, 总计: {len(urls)}"
        print(summary)
        print(f"{'='*60}")
        log_result(log_file, summary)
        
        if failed_urls:
            with open(failed_log, 'w', encoding='utf-8') as f:
                for url in failed_urls:
                    f.write(f"下载失败: {url}\n")
            print(f"\n失败的URL已保存到: {failed_log}")
        
    finally:
        print("\n保持浏览器运行,不关闭...")


if __name__ == "__main__":
    main()
=======
import subprocess
import time
import os
import glob
import psutil
import socket
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys


def is_port_open(port, host='127.0.0.1'):
    """检查端口是否开放"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False


def check_edge_debug_port(pid):
    """检查指定PID的Edge进程是否启用了远程调试端口"""
    try:
        process = psutil.Process(pid)
        cmdline = ' '.join(process.cmdline())
        
        if '--remote-debugging-port=' in cmdline:
            for arg in process.cmdline():
                if arg.startswith('--remote-debugging-port='):
                    port = int(arg.split('=')[1])
                    return True, port
        return False, None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False, None


def find_edge_debug_port():
    """查找所有启用了远程调试的Edge进程"""
    debug_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'msedge.exe' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline:
                    for arg in cmdline:
                        if '--remote-debugging-port=' in str(arg):
                            port = int(arg.split('=')[1])
                            debug_processes.append((proc.info['pid'], port))
                            break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return debug_processes


def start_edge_with_debug(debugger_port=9222, user_data_dir=None, download_dir=None):
    """启动带远程调试的Edge浏览器"""
    edge_path = r"G:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    if not os.path.exists(edge_path):
        edge_path = r"G:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    if not os.path.exists(edge_path):
        print("错误: 未找到Edge浏览器")
        return None
    
    cmd = [
        edge_path,
        f"--remote-debugging-port={debugger_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions"
    ]
    
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")
    
    print(f"启动Edge浏览器 (调试端口: {debugger_port})...")
    subprocess.Popen(cmd)

    max_wait = 30
    wait_time = 0
    while wait_time < max_wait:
        time.sleep(1)
        wait_time += 1
        
        if is_port_open(debugger_port):
            print(f"✓ Edge浏览器已启动并监听端口 {debugger_port}")
            # 额外等待2秒确保调试接口完全初始化
            time.sleep(2)
            return debugger_port
            
        print(f"等待Edge浏览器启动... ({wait_time}/{max_wait}秒)")

    print(f"✗ 等待超时，Edge浏览器可能未正确启动")
    return None


def read_failed_urls(file_path):
    """读取失败的URL列表"""
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    urls = []
    for line in lines:
        line = line.strip()
        if line.startswith("下载失败: "):
            url = line.replace("下载失败: ", "").strip()
            urls.append(url)
        elif line.startswith("http"):
            urls.append(line)
    return urls


def log_result(log_file, message):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")


def connect_to_existing_edge(debugger_port=9222, download_dir=None, max_retries=5, retry_interval=2):
    """连接到已运行的Edge浏览器"""
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debugger_port}")
    
    # 配置下载行为
    if download_dir:
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,  # 自动下载PDF而不是在浏览器中打开
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        edge_options.add_experimental_option("prefs", prefs)
    
    for attempt in range(max_retries):
        try:
            driver = webdriver.Edge(options=edge_options)
            print(f"✓ 成功连接到端口 {debugger_port} 的Edge浏览器")
            
            # 设置下载行为（通过CDP）
            if download_dir:
                driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": download_dir
                })
            
            return driver
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"✗ 连接失败 (尝试 {attempt + 1}/{max_retries}), 错误: {str(e)[:100]}")
                print(f"  {retry_interval}秒后重试...")
                time.sleep(retry_interval)
            else:
                print(f"✗ 无法连接到端口 {debugger_port}")
                print(f"  错误详情: {str(e)}")
                print(f"  提示: 请确保Edge浏览器已启动并启用了远程调试端口 {debugger_port}")
                return None


def wait_for_pdf_load(driver, timeout=30):
    """等待PDF加载完成"""
    try:
        # 方法1: 检查PDF viewer是否加载完成
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # 方法2: 检查是否是PDF内容类型
        time.sleep(2)  # 给PDF渲染一些时间
        
        # 方法3: 尝试检测PDF插件或embed元素
        try:
            pdf_elements = driver.find_elements(By.TAG_NAME, "embed") + \
                          driver.find_elements(By.TAG_NAME, "object")
            if pdf_elements:
                print("  → 检测到PDF嵌入元素")
        except:
            pass
        
        return True
    except TimeoutException:
        print("  ✗ PDF加载超时")
        return False


def save_pdf_automatically(driver, save_dir, timeout=30):
    """自动保存PDF"""
    try:
        # 使用Ctrl+S快捷键触发保存
        from selenium.webdriver.common.action_chains import ActionChains
        
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
        
        print("  → 已发送保存命令 (Ctrl+S)")
        time.sleep(2)
        
        # 按Enter确认保存（如果弹出保存对话框）
        actions.send_keys(Keys.RETURN).perform()
        time.sleep(1)
        
        return True
    except Exception as e:
        print(f"  ✗ 自动保存失败: {str(e)[:100]}")
        return False


def check_download_complete(download_dir, files_before, timeout=60):
    """检查下载是否完成"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 检查是否有临时文件
        temp_files = glob.glob(os.path.join(download_dir, "*.crdownload")) + \
                     glob.glob(os.path.join(download_dir, "*.tmp"))
        
        if not temp_files:
            # 检查是否有新文件
            files_after = set(os.listdir(download_dir))
            new_files = files_after - files_before
            
            if new_files:
                # 确保文件不是0字节
                for new_file in new_files:
                    file_path = os.path.join(download_dir, new_file)
                    if os.path.getsize(file_path) > 0:
                        return True, new_files
            
        time.sleep(0.5)
    
    return False, set()


def is_driver_valid(driver):
    """检查driver是否仍然有效"""
    try:
        # 尝试获取当前窗口句柄，如果窗口已关闭会抛出异常
        driver.current_window_handle
        return True
    except:
        return False


def reconnect_driver(debugger_port, save_dir, max_retries=3):
    """重新连接到浏览器"""
    for attempt in range(max_retries):
        try:
            print(f"  → 尝试重新连接到浏览器 (尝试 {attempt + 1}/{max_retries})...")
            new_driver = connect_to_existing_edge(debugger_port, save_dir, max_retries=2)
            if new_driver and is_driver_valid(new_driver):
                print("  ✓ 重新连接成功")
                return new_driver
        except Exception as e:
            print(f"  ✗ 重新连接失败: {str(e)[:100]}")
        time.sleep(2)
    return None


def main():
    
    import psutil
    import sys
    def get_edge_pids():
        """
        获取所有 Microsoft Edge 进程的 PID
        :return: 包含所有 Edge 进程 PID 的列表
        """
        edge_pids = []
        # 遍历系统中所有正在运行的进程
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # 检查进程名称是否为 msedge.exe
                if proc.info['name'] == 'msedge.exe':
                    edge_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 忽略无法访问的进程
                continue
        return edge_pids

    # 获取并打印 Edge 的 PID
    TARGET_PID = get_edge_pids()
    print(f"找到的 Edge 进程 PID: {TARGET_PID}")

    # 如果你只需要获取第一个找到的 PID（通常是主进程），可以这样写：
    # 传入列表中的第一个元素（主进程 PID）
    # 使用 if 确保列表不为空，避免 IndexError
    if TARGET_PID:
        has_debug, port = check_edge_debug_port(TARGET_PID[0])
    else:
        print("错误：未找到 Edge 进程，无法检查调试端口。")
        # 根据你的逻辑处理这种情况，可能是退出或抛出异常
        sys.exit(1) 


    # 配置参数
    # TARGET_PID = 2104
    DIR = os.getcwd()
    print(f"当前目录: {DIR}")
    Py_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"当前python目录: {Py_DIR}")
    error_file = os.path.join(Py_DIR, "step3_download_errors.log")
    save_dir = os.path.join(Py_DIR, "step4_retry_downloads_from_failed")
    log_file = os.path.join(Py_DIR, "step4_retry_log_failed.txt")
    failed_log = os.path.join(Py_DIR, "step4_retry_failed.txt")
    
    batch_size = 10
    batch_delay = 10
    download_timeout = 60
    page_load_timeout = 60
    pdf_load_timeout = 60
    
    os.makedirs(save_dir, exist_ok=True)
    
    urls = read_failed_urls(error_file)
    if not urls:
        print("没有找到需要重试的URL")
        return
    
    print(f"找到 {len(urls)} 个失败链接")
    log_result(log_file, f"开始重试下载,共 {len(urls)} 个链接")
    
    print(f"\n检查PID={TARGET_PID[0]}的Edge进程...")
    has_debug, port = check_edge_debug_port(TARGET_PID[0])
    
    driver = None
    
    if has_debug:
        print(f"✓ 检测到PID={TARGET_PID}的Edge已启用远程调试 (端口: {port})")
        driver = connect_to_existing_edge(port, save_dir)
    else:
        print(f"✗ PID={TARGET_PID}的Edge未启用远程调试")
        
        debug_processes = find_edge_debug_port()
        if debug_processes:
            print(f"\n发现以下Edge进程已启用远程调试:")
            for pid, port in debug_processes:
                print(f"  - PID: {pid}, 端口: {port}")
            
            print(f"\n尝试连接到PID={debug_processes[0][0]}...")
            driver = connect_to_existing_edge(debug_processes[0][1], save_dir)
        
        if driver is None:
            common_ports = [9222, 9223, 9224]
            for test_port in common_ports:
                if is_port_open(test_port):
                    print(f"\n检测到端口 {test_port} 已开放，尝试连接...")
                    driver = connect_to_existing_edge(test_port, save_dir)
                    if driver:
                        break
        
        if driver is None:
            print("\n未找到可用的调试模式Edge浏览器")
            print("\n或者,让程序启动新的Edge浏览器? (y/n): ", end='')
            
            choice = input().strip().lower()
            if choice == 'y':
                # 创建临时用户数据目录
                temp_user_data = os.path.join(Py_DIR, "edge_debug_profile")
                port = start_edge_with_debug(9222, user_data_dir=temp_user_data, download_dir=save_dir)
                if port:
                    # 增加重试次数和重试间隔
                    driver = connect_to_existing_edge(port, save_dir, max_retries=10, retry_interval=3)
            
            if driver is None:
                print("无法建立连接,程序退出")
                return
    
    driver.set_page_load_timeout(page_load_timeout)
    
    try:
        total_success = 0
        total_failed = 0
        failed_urls = []
        
        for batch_num in range(0, len(urls), batch_size):
            batch_urls = urls[batch_num:batch_num + batch_size]
            batch_index = batch_num // batch_size + 1
            
            print(f"\n{'='*60}")
            print(f"处理第 {batch_index} 批 ({len(batch_urls)} 个链接)")
            print(f"{'='*60}")
            log_result(log_file, f"开始处理第 {batch_index} 批")
            
            for i, url in enumerate(batch_urls):
                global_index = batch_num + i + 1
                print(f"\n[{global_index}/{len(urls)}] 处理: {url}")
                
                files_before = set(os.listdir(save_dir))
                
                try:
                    driver.get(url)
                    print("  → 页面加载成功")

                    if 'academic.oup.com' in url:
                        time.sleep(10)
                        print("  → 检测到academic.oup.com，已等待10秒完成安全验证")

                    # 等待PDF加载完成
                    print(f"  → 等待PDF加载完成 (最多 {pdf_load_timeout} 秒)...")
                    if wait_for_pdf_load(driver, pdf_load_timeout):
                        print("  ✓ PDF加载完成")
                        
                        # 自动保存PDF
                        save_pdf_automatically(driver, save_dir)
                        
                        # 检查下载是否完成
                        print(f"  → 等待下载完成 (最多 {download_timeout} 秒)...")
                        success, new_files = check_download_complete(save_dir, files_before, download_timeout)
                        
                        if success:
                            total_success += 1
                            print(f"  ✓ 下载成功: {', '.join(new_files)}")
                            log_result(log_file, f"成功: {url} | 文件: {', '.join(new_files)}")
                        else:
                            total_failed += 1
                            failed_urls.append(url)
                            print(f"  ✗ 下载超时或未检测到新文件")
                            log_result(log_file, f"失败: {url} | 原因: 下载超时或未检测到文件")
                    else:
                        total_failed += 1
                        failed_urls.append(url)
                        print(f"  ✗ PDF加载超时")
                        log_result(log_file, f"失败: {url} | 原因: PDF加载超时")
                        
                except TimeoutException:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ 页面加载超时")
                    log_result(log_file, f"失败: {url} | 原因: 页面加载超时")
                    
                except WebDriverException as e:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ WebDriver错误: {str(e)[:100]}")
                    log_result(log_file, f"失败: {url} | 原因: {str(e)[:200]}")
                    
                except Exception as e:
                    total_failed += 1
                    failed_urls.append(url)
                    print(f"  ✗ 未知错误: {str(e)[:100]}")
                    log_result(log_file, f"失败: {url} | 原因: {str(e)[:200]}")
                
                time.sleep(2)
            
            if batch_num + batch_size < len(urls):
                print(f"\n⏸ 等待 {batch_delay} 秒后继续下一批...")
                time.sleep(batch_delay)
        
        print(f"\n{'='*60}")
        summary = f"完成! 成功: {total_success}, 失败: {total_failed}, 总计: {len(urls)}"
        print(summary)
        print(f"{'='*60}")
        log_result(log_file, summary)
        
        if failed_urls:
            with open(failed_log, 'w', encoding='utf-8') as f:
                for url in failed_urls:
                    f.write(f"下载失败: {url}\n")
            print(f"\n失败的URL已保存到: {failed_log}")
        
    finally:
        print("\n保持浏览器运行,不关闭...")


if __name__ == "__main__":
    main()
>>>>>>> 34a7861bfc90a87a77c760888c4582ab3bf72350
