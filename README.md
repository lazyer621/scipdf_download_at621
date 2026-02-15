# scipdf_download_@621
# # SCI文献批量检索【开源/开放url】与下载工具

## 项目简介

本项目是一个完整的SCI学术文献自动化检索(已开源/已开放)文献pdf下载链接与下载工具集，支持从DOI列表批量获取文献PDF下载链接，并自动下载PDF文件。工具集包含多个Python脚本，实现了从DOI提取、链接获取、批量下载到失败重试的完整流程。

## 功能特点

- 支持从多种文献管理软件格式（EndNote .enl、RIS、纯文本）中提取DOI
- 批量获取文献PDF下载链接，支持多个数据源（CrossRef、出版商官网、Sci-Hub等）
- 多线程并发下载，提高下载效率
- 支持Selenium自动化浏览器下载，处理需要登录的网站
- 智能失败重试机制，提高下载成功率
- 自动记录下载日志，方便追踪和重试失败的下载
- 支持远程调试端口连接，可复用已打开的浏览器

## 项目结构

```
findlinks-download/
├── new.enl                          # EndNote文献库文件
├── new.txt                          # 纯文本格式的文献列表
├── step1_ris_extract_doi.ipynb      # 步骤1: 从RIS格式提取DOI的Jupyter Notebook
├── step1_new_enl_extracted_dois.txt        # 步骤1生成的文件: 从.enl文件提取的DOI
├── step1_new_txt_extracted_dois.txt        # 步骤1生成的文件: 从.txt文件提取的DOI
├── step1_all_list_dois.txt                 # 步骤1生成的文件: 提取的DOI列表
├── step1_all_list_doi.txt                  # 步骤1生成的文件: 完整的DOI列表（去重）
├── step2_scipdf_findlinks_release.py # 步骤2: PDF链接获取工具
├── step2_batch_pdf_links.txt                # 步骤2生成的文件: 批量获取的PDF下载链接
├── step3_read_txt_to_download.py    # 步骤3: 批量下载PDF文件
├── step3_pdfs_downloaded/                  # 步骤3生成的文件: 下载的PDF文件目录
├── step4_read_log_retry_download.py # 步骤4: 失败重试下载
├── step4_retry_downloads_from_failed/      # 步骤4生成的文件: 重试下载的PDF目录
├── step4_retry_failed.txt                  # 步骤4生成的文件: 重试失败的记录
├── step4_retry_log_failed.txt              # 步骤4生成的文件: 重试失败的日志
└── step5_add_num_urls.py            # 步骤5: 处理失败URL的工具
```

## 使用流程

### 步骤1: 准备DOI列表

从文献管理软件或文本文件中提取DOI，生成DOI列表文件。

**输入文件格式：**
- EndNote .enl文件
- RIS格式文件
- 纯文本文件（每行一个DOI或DOI链接）

**输出文件：**
- `step1_all_list_doi.txt`: 包含所有提取的DOI(去重后)，每行一个

**使用方法：**
1. 如果使用Jupyter Notebook提取DOI，运行 `step1_ris_extract_doi.ipynb`
2. 手动准备DOI列表文件，确保每行一个DOI

### 步骤2: 批量获取PDF下载链接

使用 `step2_scipdf_findlinks_release.py` 批量获取PDF下载链接。

**使用方法：**
```bash
python step2_scipdf_findlinks_release.py step1_all_list_doi.txt step2_batch_pdf_links.txt
```

**参数说明：**
- 第1个参数: 包含DOI列表的txt文件路径（每行一个DOI）
- 第2个参数: 输出文件路径（默认: batch_pdf_links.txt）

**功能特点：**
- 支持多线程并发请求，提高效率
- 智能延迟请求
- 输出详细的文献信息和下载链接

**输出格式：**
```
================================================================================
批量 PDF 下载链接获取结果
获取时间 : 2026-02-14 11:02:30
DOI 总数 : 20
并发线程 : 5
================================================================================

DOI: 10.1007/s10902-016-9797-y
标题: Subjective Well-Being During the 2008 Economic Crisis: Identification of Mediating and Moderating Factors
期刊: Journal of Happiness Studies
年份: 2017
作者: Gregor Gonza, Anže Burger
--------------------------------------------------------------------------------
找到 1 个 PDF 下载链接:
  1. 来源  : crossref
     版本  : publishedVersion
     链接  : http://link.springer.com/content/pdf/10.1007/s10902-016-9797-y.pdf
--------------------------------------------------------------------------------
```

### 步骤3: 批量下载PDF文件

使用 `step3_read_txt_to_download.py` 批量下载PDF文件。

**使用方法：**
```bash
python step3_read_txt_to_download.py
```

**功能特点：**
- 支持两种下载模式：
  - requests直接下载（快速，适合开放访问的PDF）
  - Selenium浏览器下载（支持需要登录的网站）
- 多线程并发下载
- 自动创建下载目录
- 记录下载日志，包括成功和失败的下载
- 支持连接到已打开的Edge浏览器

**下载模式选择：**
程序运行时会提示选择下载模式：
- 输入 'y' 使用Selenium浏览器模式
- 输入 'n' 使用requests直接下载模式

**输出目录：**
- `step3_pdfs_downloaded/`: 成功下载的PDF文件

### 步骤4: 失败重试下载

使用 `step4_read_log_retry_download.py` 重试失败的下载。

**使用方法：**
```bash
python step4_read_log_retry_download.py
```

**功能特点：**
- 自动读取下载日志，识别失败的下载
- 支持连接到已打开的Edge浏览器（通过远程调试端口）
- 智能检测Edge浏览器调试端口
- 支持自动启动带调试端口的Edge浏览器
- 记录重试日志

**输出目录：**
- `step4_retry_downloads_from_failed/`: 重试成功下载的PDF文件
- `step4_retry_failed.txt`: 重试仍然失败的记录
- `step4_retry_log_failed.txt`: 重试失败的日志

### 步骤5: 处理失败URL

使用 `step5_add_num_urls.py` 处理失败的URL。

**使用方法：**
```bash
python step5_add_num_urls.py
```

**功能特点：**
- 读取失败URL列表
- 连接到已打开的Edge浏览器
- 检测浏览器标签页是否包含PDF
- 关闭不包含PDF的标签页
- 保留包含PDF的标签页

## 环境要求

### Python版本
- Python 3.10+

### 依赖库
```
requests
beautifulsoup4
selenium
webdriver-manager
psutil
```

### 浏览器要求
- Microsoft Edge浏览器（用于Selenium模式）

### 安装依赖
```bash
pip install requests beautifulsoup4 selenium webdriver-manager psutil
```

## 注意事项

1. **版权和使用条款**
   - 本工具仅供学术研究使用，请遵守相关版权和使用条款
   - 下载的文献仅限个人学习和研究使用

2. **浏览器模式**
   - Selenium模式需要安装Edge浏览器
   - 确保EdgeDriver版本与Edge浏览器版本匹配
   - 建议使用webdriver-manager自动管理EdgeDriver

3. **失败重试**
   - 下载失败是正常现象，特别是对于需要登录的网站
   - 建议多次运行失败重试脚本
   - 对于持续失败的下载，可考虑手动下载

4. **存储空间**
   - 批量下载可能需要大量存储空间
   - 建议提前检查磁盘空间

## 常见问题

**Q: 提示EdgeDriver版本不匹配怎么办？**
A: 建议使用webdriver-manager自动管理EdgeDriver，或手动下载匹配版本的EdgeDriver并添加到系统PATH。

**Q: 下载速度慢怎么办？**
A: 可以调整并发线程数，但注意不要设置过高以免触发反爬机制。

**Q: 某些文献无法下载怎么办？**
A: 可能是文献需要订阅或登录，可以尝试使用Selenium模式并手动登录，或考虑其他获取途径。

**Q: 如何连接到已打开的Edge浏览器？**
A: 使用远程调试端口启动Edge浏览器，然后在脚本中选择连接到现有浏览器模式。

## 更新日志

- v1.0.0: 初始版本，支持基本的DOI提取、链接获取和PDF下载功能

## 许可证

本项目仅供学术研究使用，请勿用于商业用途。

## 联系方式
邮箱：xiaoliuzi216@gmail.com
WeChat_ID: Civil-IT_a621

如有问题或建议，欢迎提出Issue。

## ⭐ 支持

如果您觉得这个项目有帮助，请考虑：
- 给它一个 **star** ⭐
- 或请我喝杯咖啡
<img width="372" height="508" alt="付费支持" src="https://github.com/user-attachments/assets/50369da2-0724-4da1-9181-43ac38e0574e" />
<br>感谢您的支持，祝您生活愉快！



