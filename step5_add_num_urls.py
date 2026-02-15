<<<<<<< HEAD
import subprocess
import time
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
import psutil


def read_failed_urls(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    urls = []
    for line in lines:
        if line.startswith("下载失败: "):
            url = line.replace("下载失败: ", "").strip()
            urls.append(url)
    return urls


def connect_to_existing_edge(debug_port=9222):
    """连接到已打开的Edge浏览器"""
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
    driver = webdriver.Edge(options=edge_options)
    return driver


def check_tab_has_pdf(driver, window_handle):
    """检查标签页是否包含PDF"""
    try:
        driver.switch_to.window(window_handle)
        time.sleep(2)
        
        current_url = driver.current_url.lower()
        if '.pdf' in current_url:
            return True
        
        title = driver.title.lower()
        if 'pdf' in title or '.pdf' in title:
            return True
        
        try:
            pdf_embeds = driver.find_elements(By.TAG_NAME, "embed")
            for embed in pdf_embeds:
                embed_type = embed.get_attribute("type")
                if embed_type and "pdf" in embed_type.lower():
                    return True
        except:
            pass
        
        try:
            content_type = driver.execute_script(
                "return document.contentType || document.mimeType;"
            )
            if content_type and "pdf" in content_type.lower():
                return True
        except:
            pass
        
        return False
    except Exception as e:
        print(f"检测标签页时出错: {e}")
        return False


def close_non_pdf_tabs(driver, keep_first_tab=True):
    """关闭所有未检测到PDF的标签页"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    closed_count = 0
    
    print(f"\n开始检测 {len(all_handles)} 个标签页...")
    
    for i, handle in enumerate(all_handles):
        if keep_first_tab and i == 0:
            continue
        
        has_pdf = check_tab_has_pdf(driver, handle)
        
        if not has_pdf:
            try:
                driver.switch_to.window(handle)
                current_url = driver.current_url
                print(f"关闭标签页 [{i+1}]: {current_url[:80]}...")
                driver.close()
                closed_count += 1
            except Exception as e:
                print(f"关闭标签页失败: {e}")
        else:
            print(f"保留标签页 [{i+1}]: 检测到PDF")
    
    remaining_handles = driver.window_handles
    if remaining_handles:
        if original_handle in remaining_handles:
            driver.switch_to.window(original_handle)
        else:
            driver.switch_to.window(remaining_handles[0])
    
    print(f"已关闭 {closed_count} 个非PDF标签页")
    return closed_count


def download_pdfs_from_tabs(driver):
    """遍历所有标签页并尝试下载PDF"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    download_count = 0
    
    print(f"\n开始检测并下载 {len(all_handles)} 个标签页中的PDF...")
    
    for i, handle in enumerate(all_handles):
        if i == 0:  # 跳过第一个标签页
            continue
            
        try:
            driver.switch_to.window(handle)
            current_url = driver.current_url
            
            # 检查是否为PDF
            if check_tab_has_pdf(driver, handle):
                print(f"\n标签页 [{i+1}] 检测到PDF: {current_url[:80]}")
                
                # 尝试触发下载
                try:
                    # 方法1: 使用Ctrl+S快捷键
                    driver.execute_script("window.print();")
                    time.sleep(1)
                    
                    # 或者尝试直接下载
                    driver.execute_script("""
                        var link = document.createElement('a');
                        link.href = window.location.href;
                        link.download = '';
                        link.click();
                    """)
                    
                    download_count += 1
                    print(f"已触发下载")
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"下载触发失败: {e}")
            else:
                print(f"标签页 [{i+1}] 未检测到PDF")
                
        except Exception as e:
            print(f"处理标签页时出错: {e}")
    
    # 切换回原始标签页
    if original_handle in driver.window_handles:
        driver.switch_to.window(original_handle)
    
    print(f"\n共触发 {download_count} 个PDF下载")
    return download_count


def close_all_pdf_tabs(driver, keep_first_tab=True):
    """关闭所有PDF标签页"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    closed_count = 0
    
    print(f"\n开始关闭PDF标签页...")
    
    for i, handle in enumerate(all_handles):
        if keep_first_tab and i == 0:
            continue
        
        try:
            driver.switch_to.window(handle)
            driver.close()
            closed_count += 1
            print(f"已关闭标签页 [{i+1}]")
        except Exception as e:
            print(f"关闭标签页失败: {e}")
    
    remaining_handles = driver.window_handles
    if remaining_handles:
        if original_handle in remaining_handles:
            driver.switch_to.window(original_handle)
        else:
            driver.switch_to.window(remaining_handles[0])
    
    print(f"已关闭 {closed_count} 个标签页")
    return closed_count


def main():
    import os
    DIR = os.path.dirname(os.path.abspath(__file__))
    error_file = os.path.join(DIR, "step4_retry_failed.txt")
    
    batch_size = 50
    debug_port = 9222
    
    urls = read_failed_urls(error_file)
    print(f"找到 {len(urls)} 个失败链接")
    
    print(f"\n正在执行: msedge.exe --remote-debugging-port={debug_port}'")
    cmd = [
        "msedge.exe",
        f"--remote-debugging-port={debug_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions"
    ]
    subprocess.run(cmd, shell=True)
    input("启动完成后，请按下回车继续...")
    
    try:
        driver = connect_to_existing_edge(debug_port)
        print("成功连接到Edge浏览器")
    except Exception as e:
        print(f"连接失败: {e}")
        return
    
    success_count = 0
    total_batches = (len(urls) + batch_size - 1) // batch_size
    
    start_batch_num = 0
    if start_batch_num >= total_batches:
        print(f"错误: 起始批次 {start_batch_num + 1} 超出总批次 {total_batches}")
        return
    
    for batch_num in range(start_batch_num, total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(urls))
        batch_urls = urls[start_idx:end_idx]
        
        print(f"\n{'='*60}")
        print(f"第 {batch_num + 1}/{total_batches} 批 - 加载 {len(batch_urls)} 个链接")
        print(f"{'='*60}")
        
        for i, url in enumerate(batch_urls):
            try:
                try:
                    driver.switch_to.new_window('tab')
                    driver.get(url)
                except AttributeError:
                    driver.execute_script("window.open('about:blank', '_blank');")
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.get(url)
                
                success_count += 1
                print(f"[{start_idx + i + 1}/{len(urls)}] 成功打开: {url}")
                time.sleep(0.25)
                
            except Exception as e:
                print(f"打开URL失败: {url}, 错误: {e}")
        
        print("\n等待页面加载...")
        time.sleep(5)
        
        # 关闭非PDF标签页
        print("\n" + "="*60)
        user_input = input("输入 'y' 自动关闭非PDF标签页, 其他键跳过: ").strip().lower()
        if user_input == 'y':
            close_non_pdf_tabs(driver, keep_first_tab=True)
            time.sleep(0.5)
        else:
            print("跳过关闭非PDF标签页")
        
        # 下载PDF
        print("\n" + "="*60)
        download_input = input("输入 'd' 自动检测并下载PDF文件, 其他键跳过: ").strip().lower()
        if download_input == 'd':
            download_pdfs_from_tabs(driver)
            time.sleep(0.5)
            
            # 下载完成后询问是否关闭所有PDF标签页
            print("\n" + "="*60)
            close_input = input("输入 'c' 关闭所有PDF标签页, 其他键跳过: ").strip().lower()
            if close_input == 'c':
                close_all_pdf_tabs(driver, keep_first_tab=True)
                time.sleep(0.5)
                print("已关闭所有PDF标签页")
            else:
                print("跳过关闭PDF标签页")
        else:
            print("跳过下载PDF")
        
        # 继续下一批 - 这个逻辑在所有操作之后
        if batch_num < total_batches - 1:
            print("\n" + "="*60)
            continue_input = input("输入 'n' 继续下一批, 其他键退出: ").strip().lower()
            if continue_input != 'n':
                print("用户取消,程序终止")
                break
        else:
            print("\n已完成所有批次")
    
    print(f"\n{'='*60}")
    print(f"总结: 成功打开 {success_count}/{len(urls)} 个链接")
    print(f"{'='*60}")
    
    driver.quit()


if __name__ == "__main__":
    main()
=======
import subprocess
import time
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
import psutil


def read_failed_urls(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    urls = []
    for line in lines:
        if line.startswith("下载失败: "):
            url = line.replace("下载失败: ", "").strip()
            urls.append(url)
    return urls


def connect_to_existing_edge(debug_port=9222):
    """连接到已打开的Edge浏览器"""
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")
    driver = webdriver.Edge(options=edge_options)
    return driver


def check_tab_has_pdf(driver, window_handle):
    """检查标签页是否包含PDF"""
    try:
        driver.switch_to.window(window_handle)
        time.sleep(2)
        
        current_url = driver.current_url.lower()
        if '.pdf' in current_url:
            return True
        
        title = driver.title.lower()
        if 'pdf' in title or '.pdf' in title:
            return True
        
        try:
            pdf_embeds = driver.find_elements(By.TAG_NAME, "embed")
            for embed in pdf_embeds:
                embed_type = embed.get_attribute("type")
                if embed_type and "pdf" in embed_type.lower():
                    return True
        except:
            pass
        
        try:
            content_type = driver.execute_script(
                "return document.contentType || document.mimeType;"
            )
            if content_type and "pdf" in content_type.lower():
                return True
        except:
            pass
        
        return False
    except Exception as e:
        print(f"检测标签页时出错: {e}")
        return False


def close_non_pdf_tabs(driver, keep_first_tab=True):
    """关闭所有未检测到PDF的标签页"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    closed_count = 0
    
    print(f"\n开始检测 {len(all_handles)} 个标签页...")
    
    for i, handle in enumerate(all_handles):
        if keep_first_tab and i == 0:
            continue
        
        has_pdf = check_tab_has_pdf(driver, handle)
        
        if not has_pdf:
            try:
                driver.switch_to.window(handle)
                current_url = driver.current_url
                print(f"关闭标签页 [{i+1}]: {current_url[:80]}...")
                driver.close()
                closed_count += 1
            except Exception as e:
                print(f"关闭标签页失败: {e}")
        else:
            print(f"保留标签页 [{i+1}]: 检测到PDF")
    
    remaining_handles = driver.window_handles
    if remaining_handles:
        if original_handle in remaining_handles:
            driver.switch_to.window(original_handle)
        else:
            driver.switch_to.window(remaining_handles[0])
    
    print(f"已关闭 {closed_count} 个非PDF标签页")
    return closed_count


def download_pdfs_from_tabs(driver):
    """遍历所有标签页并尝试下载PDF"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    download_count = 0
    
    print(f"\n开始检测并下载 {len(all_handles)} 个标签页中的PDF...")
    
    for i, handle in enumerate(all_handles):
        if i == 0:  # 跳过第一个标签页
            continue
            
        try:
            driver.switch_to.window(handle)
            current_url = driver.current_url
            
            # 检查是否为PDF
            if check_tab_has_pdf(driver, handle):
                print(f"\n标签页 [{i+1}] 检测到PDF: {current_url[:80]}")
                
                # 尝试触发下载
                try:
                    # 方法1: 使用Ctrl+S快捷键
                    driver.execute_script("window.print();")
                    time.sleep(1)
                    
                    # 或者尝试直接下载
                    driver.execute_script("""
                        var link = document.createElement('a');
                        link.href = window.location.href;
                        link.download = '';
                        link.click();
                    """)
                    
                    download_count += 1
                    print(f"已触发下载")
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"下载触发失败: {e}")
            else:
                print(f"标签页 [{i+1}] 未检测到PDF")
                
        except Exception as e:
            print(f"处理标签页时出错: {e}")
    
    # 切换回原始标签页
    if original_handle in driver.window_handles:
        driver.switch_to.window(original_handle)
    
    print(f"\n共触发 {download_count} 个PDF下载")
    return download_count


def close_all_pdf_tabs(driver, keep_first_tab=True):
    """关闭所有PDF标签页"""
    all_handles = driver.window_handles
    original_handle = driver.current_window_handle
    closed_count = 0
    
    print(f"\n开始关闭PDF标签页...")
    
    for i, handle in enumerate(all_handles):
        if keep_first_tab and i == 0:
            continue
        
        try:
            driver.switch_to.window(handle)
            driver.close()
            closed_count += 1
            print(f"已关闭标签页 [{i+1}]")
        except Exception as e:
            print(f"关闭标签页失败: {e}")
    
    remaining_handles = driver.window_handles
    if remaining_handles:
        if original_handle in remaining_handles:
            driver.switch_to.window(original_handle)
        else:
            driver.switch_to.window(remaining_handles[0])
    
    print(f"已关闭 {closed_count} 个标签页")
    return closed_count


def main():
    import os
    DIR = os.path.dirname(os.path.abspath(__file__))
    error_file = os.path.join(DIR, "step4_retry_failed.txt")
    
    batch_size = 50
    debug_port = 9222
    
    urls = read_failed_urls(error_file)
    print(f"找到 {len(urls)} 个失败链接")
    
    print(f"\n正在执行: msedge.exe --remote-debugging-port={debug_port}'")
    cmd = [
        "msedge.exe",
        f"--remote-debugging-port={debug_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions"
    ]
    subprocess.run(cmd, shell=True)
    input("启动完成后，请按下回车继续...")
    
    try:
        driver = connect_to_existing_edge(debug_port)
        print("成功连接到Edge浏览器")
    except Exception as e:
        print(f"连接失败: {e}")
        return
    
    success_count = 0
    total_batches = (len(urls) + batch_size - 1) // batch_size
    
    start_batch_num = 0
    if start_batch_num >= total_batches:
        print(f"错误: 起始批次 {start_batch_num + 1} 超出总批次 {total_batches}")
        return
    
    for batch_num in range(start_batch_num, total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(urls))
        batch_urls = urls[start_idx:end_idx]
        
        print(f"\n{'='*60}")
        print(f"第 {batch_num + 1}/{total_batches} 批 - 加载 {len(batch_urls)} 个链接")
        print(f"{'='*60}")
        
        for i, url in enumerate(batch_urls):
            try:
                try:
                    driver.switch_to.new_window('tab')
                    driver.get(url)
                except AttributeError:
                    driver.execute_script("window.open('about:blank', '_blank');")
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.get(url)
                
                success_count += 1
                print(f"[{start_idx + i + 1}/{len(urls)}] 成功打开: {url}")
                time.sleep(0.25)
                
            except Exception as e:
                print(f"打开URL失败: {url}, 错误: {e}")
        
        print("\n等待页面加载...")
        time.sleep(5)
        
        # 关闭非PDF标签页
        print("\n" + "="*60)
        user_input = input("输入 'y' 自动关闭非PDF标签页, 其他键跳过: ").strip().lower()
        if user_input == 'y':
            close_non_pdf_tabs(driver, keep_first_tab=True)
            time.sleep(0.5)
        else:
            print("跳过关闭非PDF标签页")
        
        # 下载PDF
        print("\n" + "="*60)
        download_input = input("输入 'd' 自动检测并下载PDF文件, 其他键跳过: ").strip().lower()
        if download_input == 'd':
            download_pdfs_from_tabs(driver)
            time.sleep(0.5)
            
            # 下载完成后询问是否关闭所有PDF标签页
            print("\n" + "="*60)
            close_input = input("输入 'c' 关闭所有PDF标签页, 其他键跳过: ").strip().lower()
            if close_input == 'c':
                close_all_pdf_tabs(driver, keep_first_tab=True)
                time.sleep(0.5)
                print("已关闭所有PDF标签页")
            else:
                print("跳过关闭PDF标签页")
        else:
            print("跳过下载PDF")
        
        # 继续下一批 - 这个逻辑在所有操作之后
        if batch_num < total_batches - 1:
            print("\n" + "="*60)
            continue_input = input("输入 'n' 继续下一批, 其他键退出: ").strip().lower()
            if continue_input != 'n':
                print("用户取消,程序终止")
                break
        else:
            print("\n已完成所有批次")
    
    print(f"\n{'='*60}")
    print(f"总结: 成功打开 {success_count}/{len(urls)} 个链接")
    print(f"{'='*60}")
    
    driver.quit()


if __name__ == "__main__":
    main()
>>>>>>> 34a7861bfc90a87a77c760888c4582ab3bf72350
