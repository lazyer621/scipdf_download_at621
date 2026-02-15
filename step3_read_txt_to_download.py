import os
import sys
import time
import glob
import shutil
import requests
from urllib.parse import urlparse, unquote
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import queue


# ========== 浏览器相关函数 ==========
def create_browser(download_dir):
    """创建Edge浏览器实例，添加更多错误处理和反检测措施"""
    edge_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    edge_options.add_experimental_option("prefs", prefs)

    # 反自动化检测措施
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)
    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--disable-dev-shm-usage")
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--window-size=1920,1080")
    edge_options.add_argument("--start-maximized")
    edge_options.add_argument("--disable-infobars")
    edge_options.add_argument("--disable-extensions")
    edge_options.add_argument("--disable-software-rasterizer")

    # 使用真实浏览器User-Agent
    edge_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )

    # 禁用日志输出
    edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    edge_options.add_argument("--log-level=3")

    try:
        # 尝试使用webdriver_manager自动管理EdgeDriver
        try:
            service = Service(EdgeChromiumDriverManager().install())
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            print(f"使用webdriver_manager失败: {e}")
            print("尝试使用系统默认EdgeDriver...")
            driver = webdriver.Edge(options=edge_options)

        # 执行多个反检测脚本
        stealth_script = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        window.chrome = {runtime: {}};
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({state: 'granted'})
            })
        });
        """
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": stealth_script
        })

        # 设置页面加载超时
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(30)

        return driver
    except Exception as e:
        print(f"Edge浏览器创建失败: {e}")
        print("\n可能的解决方案:")
        print("1. 检查Edge浏览器是否已正确安装")
        print("2. 确保EdgeDriver版本与Edge浏览器版本匹配")
        print("3. 尝试手动下载匹配的EdgeDriver并添加到系统PATH")
        print("4. 或者输入'n'不使用浏览器模式，仅使用requests下载")
        raise


def connect_to_existing_browser(download_dir):
    """连接到已打开的Edge浏览器"""
    edge_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    edge_options.add_experimental_option("prefs", prefs)

    # 连接到现有浏览器的关键参数
    edge_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    edge_options.add_argument("--disable-blink-features=AutomationControlled")
    edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_options.add_experimental_option("useAutomationExtension", False)

    try:
        driver = webdriver.Edge(options=edge_options)
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(30)
        return driver
    except Exception as e:
        print(f"连接到现有浏览器失败: {e}")
        print("\n请确保已按以下步骤操作:")
        print("1. 关闭所有Edge浏览器窗口")
        print("2. 以管理员身份运行命令提示符")
        print("3. 执行以下命令启动Edge浏览器:")
        print('   msedge.exe --remote-debugging-port=9222 --user-data-dir="C:\\EdgeDebug"')
        print("4. 浏览器启动后，再运行此程序")
        raise


def wait_for_download(download_dir, filename, timeout=120):
    """等待文件下载完成"""
    start_time = time.time()
    file_path = os.path.join(download_dir, filename)
    while time.time() - start_time < timeout:
        crdownload_files = glob.glob(os.path.join(download_dir, "*.crdownload"))
        if os.path.exists(file_path) and not crdownload_files:
            time.sleep(1)
            if os.path.getsize(file_path) > 0:
                return True
        time.sleep(1)
    return False


def check_and_handle_captcha(driver, max_attempts=3):
    """检测并处理验证码，返回是否成功通过"""
    for attempt in range(max_attempts):
        page_source = driver.page_source.lower()

        # 检测常见的验证码关键词
        captcha_keywords = ['challenge', 'captcha', '验证', '人机验证', 'cloudflare', 'cf-challenge']
        has_captcha = any(keyword in page_source for keyword in captcha_keywords)

        if not has_captcha:
            return True

        print(f"  检测到验证码 (尝试 {attempt + 1}/{max_attempts})")

        # 等待一段时间让验证码加载
        time.sleep(5)

        # 检查是否有手动验证按钮
        try:
            # 查找常见的验证按钮
            verify_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Verify') or contains(text(), '验证') or contains(@class, 'challenge')]")
            if verify_buttons:
                print("  找到验证按钮，请手动点击...")
                time.sleep(15)
        except:
            pass

        # 提示用户手动处理
        print("  请在浏览器中手动完成验证，然后按回车继续...")
        input("  验证完成后按回车键...")

        # 检查验证是否通过
        page_source = driver.page_source.lower()
        has_captcha = any(keyword in page_source for keyword in captcha_keywords)

        if not has_captcha:
            print("  验证通过！")
            return True

    print("  多次尝试后仍无法通过验证")
    return False


def download_with_browser(driver, url, save_directory, filename):
    """使用浏览器下载文件（使用新标签页方式）"""
    file_path = os.path.join(save_directory, filename)
    before_files = set(os.listdir(save_directory))

    # 保存当前标签页句柄
    original_window = driver.current_window_handle

    # 创建新标签页
    driver.execute_script("window.open('');")

    # 切换到新标签页
    new_window = [window for window in driver.window_handles if window != original_window][0]
    driver.switch_to.window(new_window)

    try:
        print(f"  正在新标签页访问: {url}")
        driver.get(url)

        # 等待页面加载
        time.sleep(3)

        # 检查并处理验证码
        if not check_and_handle_captcha(driver):
            print("  验证失败，关闭标签页，跳过此文件")
            driver.close()
            driver.switch_to.window(original_window)
            return False

        # 等待下载开始
        print("  等待下载开始...")
        time.sleep(5)

        # 检查下载是否完成
        if wait_for_download(save_directory, filename, timeout=120):
            print("  下载完成，关闭标签页")
            driver.close()
            driver.switch_to.window(original_window)
            return True

        # 检查新文件
        print("  检查下载的文件...")
        time.sleep(5)
        after_files = set(os.listdir(save_directory))
        new_pdfs = [f for f in (after_files - before_files) if f.endswith('.pdf')]
        if new_pdfs:
            new_path = os.path.join(save_directory, new_pdfs[0])
            if new_pdfs[0] != filename and not os.path.exists(file_path):
                shutil.move(new_path, file_path)
            print("  下载完成，关闭标签页")
            driver.close()
            driver.switch_to.window(original_window)
            return True

        print("  未检测到下载文件，关闭标签页")
        driver.close()
        driver.switch_to.window(original_window)
        return False
    except Exception as e:
        print(f"  [浏览器] 下载过程中出错: {e}")
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except:
            pass
        return False


# ========== requests 下载函数 ==========
def download_with_requests(url, file_path, filename):
    """使用 requests 下载文件（优先方案）"""
    # 检查文件是否被占用
    if os.path.exists(file_path):
        try:
            # 尝试以写入模式打开文件，如果失败则说明文件被占用
            with open(file_path, 'ab') as f:
                pass
        except IOError:
            # 文件被占用，生成临时文件名
            base, ext = os.path.splitext(filename)
            temp_filename = f"{base}_temp{ext}"
            file_path = os.path.join(os.path.dirname(file_path), temp_filename)
            print(f"  [警告] 文件被占用，使用临时文件名: {temp_filename}")

    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    }

    try:
        with session.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True) as response:
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            sys.stdout.write(f"\r  进度: {progress:.2f}%")
                            sys.stdout.flush()

            if downloaded_size == 0:
                os.remove(file_path)
                return False

            with open(file_path, 'rb') as f:
                if f.read(5) != b'%PDF-':
                    os.remove(file_path)
                    return False

            print()
            return True
    except requests.exceptions.RequestException as e:
        # 如果下载失败且创建了临时文件，删除它
        if '_temp' in file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise


# ========== 主下载逻辑 ==========
def download_file_hybrid(url, save_directory, log_file, driver=None):
    """混合下载：先 requests，403 则切换浏览器"""
    parsed_url = urlparse(url)
    filename = unquote(os.path.basename(parsed_url.path))
    if not filename or '.' not in filename:
        filename = 'downloaded_file.pdf'

    file_path = os.path.join(save_directory, filename)

    # 检查文件是否已存在
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"  文件 {filename} 已存在，跳过。")
        return True

    # 第一步：尝试 requests
    try:
        print(f"  [requests] 尝试直接下载...")
        if download_with_requests(url, file_path, filename):
            print(f"  ✓ {filename} 通过 requests 下载成功!")
            return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"  [requests] 收到 403，切换到浏览器模式...")
        else:
            print(f"  [requests] HTTP错误: {e}")
    except Exception as e:
        print(f"  [requests] 失败: {e}")

    # 第二步：使用浏览器下载
    if driver:
        try:
            print(f"  [浏览器] 尝试通过浏览器下载...")
            if download_with_browser(driver, url, save_directory, filename):
                # 验证 PDF
                actual_path = os.path.join(save_directory, filename)
                if os.path.exists(actual_path):
                    with open(actual_path, 'rb') as f:
                        if f.read(5) == b'%PDF-':
                            print(f"  ✓ {filename} 通过浏览器下载成功!")
                            return True
                        else:
                            os.remove(actual_path)
            print(f"  ✗ {filename} 浏览器下载也失败了")
        except Exception as e:
            print(f"  [浏览器] 错误: {e}")

    with open(log_file, 'a', encoding='utf-8') as log:
        log.write(f"下载失败: {url}\n")
    return False


def main():
    DIR = os.getcwd()
    print(f"当前目录: {DIR}")
    Py_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"当前python目录: {Py_DIR}")
    txt_path = os.path.join(Py_DIR, "step2_batch_pdf_links.txt")
    save_directory = os.path.join(Py_DIR, "step3_pdfs_downloaded")
    log_file = os.path.join(Py_DIR, 'step3_download_errors.log')

    os.makedirs(save_directory, exist_ok=True)

    # 从第1行开始读取
    start_line = 1
    urls_to_download = []

    print(f"正在从第 {start_line} 行开始读取文件...")
    with open(txt_path, 'r', encoding='utf-8') as file:
        for i, line in enumerate(file, start=1):  # 从1开始计数
            if i < start_line:
                continue
            line = line.strip()
            if line.startswith("链接  :") and line.endswith(".pdf"):
                url = line.split("链接  :")[1]
                urls_to_download.append((i, url))

    print(f"共找到 {len(urls_to_download)} 个PDF链接\n")

    # 线程安全的计数器和锁
    success_count = 0
    fail_count = 0
    counter_lock = Lock()
    log_lock = Lock()

    # 询问线程数
    thread_count = input("请输入并发下载线程数 (默认3): ").strip()
    try:
        thread_count = int(thread_count) if thread_count else 3
        thread_count = max(1, min(thread_count, 10))  # 限制在1-10之间
    except ValueError:
        thread_count = 3
    print(f"将使用 {thread_count} 个线程进行下载\n")

    driver = None
    use_existing_browser = False

    # 添加用户选择是否使用浏览器
    use_browser = input("是否使用浏览器作为备用下载方式？(y/n，默认n): ").strip().lower()
    use_browser = use_browser == 'y'

    if use_browser:
        # 询问用户是使用新浏览器还是连接到现有浏览器
        browser_mode = input("使用模式: 1-创建新浏览器 2-连接到现有浏览器 (默认1): ").strip()
        use_existing_browser = browser_mode == '2'

        try:
            if use_existing_browser:
                print("\n尝试连接到现有浏览器...")
                print("请确保已按以下步骤操作:")
                print("1. 关闭所有Edge浏览器窗口")
                print("2. 以管理员身份运行命令提示符")
                print("3. 执行以下命令启动Edge浏览器:")
                print('   msedge.exe --remote-debugging-port=9222 --user-data-dir="C:\\EdgeDebug"')
                print("4. 浏览器启动后，在此处按回车继续...")
                input()

                driver = connect_to_existing_browser(save_directory)
                print("\n已成功连接到现有浏览器！")
            else:
                # 预先启动浏览器作为备用
                print("\n正在启动备用浏览器...")
                driver = create_browser(save_directory)
                print("浏览器已启动，正在访问网站...")

                # 添加页面加载超时和更详细的日志
                try:
                    driver.get("https://sci-hub.red")
                    print("网站访问成功，等待页面完全加载...")
                    time.sleep(3)
                    print("浏览器就绪！\n")
                except Exception as e:
                    print(f"网站访问超时或失败({e})，浏览器仍可使用，继续执行下载任务...\n")
        except Exception as e:
            print(f"浏览器初始化失败({e})，将仅使用 requests 模式\n")
            driver = None

    # 创建线程安全的下载函数
    def download_task(line_num, url):
        nonlocal success_count, fail_count
        print(f"\n[{line_num}] 开始下载: {url}")
        try:
            if download_file_hybrid(url, save_directory, log_file, driver):
                with counter_lock:
                    success_count += 1
                print(f"\n[{line_num}] 下载成功")
                return True
            else:
                with counter_lock:
                    fail_count += 1
                print(f"\n[{line_num}] 下载失败")
                return False
        except Exception as e:
            with counter_lock:
                fail_count += 1
            with log_lock:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"[{line_num}] 下载异常: {url}\n错误: {str(e)}\n")
            print(f"\n[{line_num}] 下载异常: {e}")
            return False

    try:
        # 使用线程池进行下载
        print(f"开始多线程下载，共 {len(urls_to_download)} 个任务\n")

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            # 提交所有下载任务
            future_to_url = {executor.submit(download_task, line_num, url): (line_num, url) 
                           for line_num, url in urls_to_download}

            # 等待所有任务完成
            for future in as_completed(future_to_url):
                line_num, url = future_to_url[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"\n[{line_num}] 任务执行异常: {e}")
                    with counter_lock:
                        fail_count += 1
    finally:
        # 只有当不是连接到现有浏览器时才退出浏览器
        if driver and not use_existing_browser:
            print("\n关闭浏览器...")
            driver.quit()
        elif driver:
            print("\n保持现有浏览器运行，不关闭它。")

    print(f"\n{'='*50}")
    print(f"成功: {success_count} | 失败: {fail_count}")
    print(f"日志: {log_file}")


if __name__ == "__main__":
    main()
