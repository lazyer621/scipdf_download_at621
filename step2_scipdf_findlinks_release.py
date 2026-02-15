<<<<<<< HEAD
# =============================================================================
# SCI文献PDF下载链接获取工具
# 用法: python doi_pdf_finder.py doi_list.txt batch_pdf_links.txt
# 参数1: 包含DOI列表的txt文件路径 (每行一个DOI)
# 参数2: 输出文件路径 (默认: batch_pdf_links.txt)
# =============================================================================

import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    print("警告: 未安装beautifulsoup4, 部分功能(出版商/Sci-Hub)将不可用")
    print("安装方法: pip install beautifulsoup4")


# =============================================================================
# PDFLinkFinder 核心类
# =============================================================================
class PDFLinkFinder:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        self.session = requests.Session()

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0",
        ]

        self.session.headers.update(
            {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
                "DNT": "1",
                "Sec-Fetch-User": "?1",
                "Sec-Ch-Ua": '"Chromium";v="94", " Not;A Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )

        self.session.cookies.update(
            {
                "cookie_consent": "true",
                "gdpr": "1",
            }
        )

        os.makedirs(self.output_dir, exist_ok=True)
        self.cancel_download = False
        self.min_delay = 1
        self.max_delay = 3
        self.last_request_time = 0

    # -----------------------------------------------------------------
    # 内部工具方法
    # -----------------------------------------------------------------
    @staticmethod
    def _log(message):
        print(message)

    def _delay_request(self):
        """请求间随机延迟, 防止封禁"""
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()

    def _rotate_ua(self):
        """随机更换 User-Agent"""
        self.session.headers.update({"User-Agent": random.choice(self.user_agents)})

    # -----------------------------------------------------------------
    # DOI 清洗
    # -----------------------------------------------------------------
    def clean_doi(self, doi):
        if not doi:
            return None
        doi = doi.strip()
        if doi.startswith("http"):
            if "doi.org/" in doi:
                doi = doi.split("doi.org/")[-1]
            elif "/doi/" in doi:
                doi = doi.split("/doi/")[-1]
                doi = doi.split("?")[0]
        match = re.match(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", doi, re.IGNORECASE)
        return match.group(0) if match else None

    # -----------------------------------------------------------------
    # 元数据获取 (Crossref)
    # -----------------------------------------------------------------
    def get_article_metadata(self, doi, timeout=10):
        api_url = f"https://api.crossref.org/works/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(api_url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "ok":
                return None
            item = data.get("message", {})
            title = item.get("title", ["未知标题"])[0]
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}"
                for a in item.get("author", [])
            ]
            journal = item.get("container-title", ["未知期刊"])
            journal = journal[0] if journal else "未知期刊"
            date_parts = item.get(
                "published-print", item.get("published-online", {})
            ).get("date-parts", [[""]])
            year = date_parts[0][0] if date_parts and date_parts[0] else ""
            return {
                "doi": doi,
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
            }
        except Exception as e:
            self._log(f"  [元数据] 获取失败: {e}")
            return None

    # -----------------------------------------------------------------
    # 来源1: Zotero Open Access
    # -----------------------------------------------------------------
    def get_open_access_pdf_urls(self, doi, timeout=10):
        self._log(f"  [OA] 正在查询 Zotero OA …")
        url = "https://services.zotero.org/oa/search"
        try:
            self._delay_request()
            self._rotate_ua()
            self.session.headers.update(
                {
                    "Referer": "https://www.zotero.org/",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Origin": "https://www.zotero.org",
                }
            )
            resp = self.session.post(
                url,
                data=json.dumps({"doi": doi}),
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
            urls = []
            for item in raw:
                if isinstance(item, str):
                    urls.append(
                        {
                            "url": item,
                            "pageURL": "",
                            "version": "publishedVersion",
                            "source": "openaccess",
                        }
                    )
                elif isinstance(item, dict) and "url" in item:
                    item.setdefault("source", "openaccess")
                    urls.append(item)
            self._log(f"  [OA] 找到 {len(urls)} 个链接")
            return urls
        except Exception as e:
            self._log(f"  [OA] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源2: Unpaywall
    # -----------------------------------------------------------------
    def get_unpaywall_pdf_urls(self, doi, timeout=10):
        self._log(f"  [Unpaywall] 正在查询 …")
        url = f"https://api.unpaywall.org/v2/{doi}?email=postinbing@outlook.com"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            if data.get("is_oa"):
                best = data.get("best_oa_location")
                if best and best.get("url_for_pdf"):
                    pdf_urls.append(
                        {
                            "url": best["url_for_pdf"],
                            "pageURL": best.get("url", ""),
                            "version": best.get("version", "unknown"),
                            "source": "unpaywall",
                        }
                    )
                for loc in data.get("oa_locations", []):
                    if loc.get("url_for_pdf") and loc != best:
                        pdf_urls.append(
                            {
                                "url": loc["url_for_pdf"],
                                "pageURL": loc.get("url", ""),
                                "version": loc.get("version", "unknown"),
                                "source": "unpaywall",
                            }
                        )
            self._log(f"  [Unpaywall] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [Unpaywall] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源3: Crossref
    # -----------------------------------------------------------------
    def get_crossref_pdf_urls(self, doi, timeout=10):
        self._log(f"  [Crossref] 正在查询 …")
        url = f"https://api.crossref.org/works/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            if data.get("status") == "ok":
                for link in data.get("message", {}).get("link", []):
                    if "application/pdf" in link.get("content-type", ""):
                        pdf_urls.append(
                            {
                                "url": link.get("URL", ""),
                                "pageURL": "",
                                "version": "publishedVersion",
                                "source": "crossref",
                            }
                        )
            self._log(f"  [Crossref] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [Crossref] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源4: Sci-Hub
    # -----------------------------------------------------------------
    def get_scihub_pdf_urls(self, doi, timeout=10):
        if BeautifulSoup is None:
            self._log(f"  [Sci-Hub] 跳过 (未安装 beautifulsoup4)")
            return []

        self._log(f"  [Sci-Hub] 正在查询 …")
        mirrors = [
            "https://sci-hub.se/",
            "https://sci-hub.st/",
            "https://sci-hub.ru/",
            "https://sci-hub.box/",
            "https://sci-hub.red/",
            "https://sci-hub.ren/",
            "https://sci-hub.ee/",
            "https://sci-hub.wf/",
        ]
        random.shuffle(mirrors)
        pdf_urls = []

        for base in mirrors:
            try:
                self._delay_request()
                self._rotate_ua()
                self.session.headers.update({"Referer": base})
                resp = self.session.get(f"{base}{doi}", timeout=timeout)
                if resp.status_code == 403:
                    continue
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                elem = soup.find("embed", type="application/pdf") or soup.find(
                    "iframe", src=re.compile(r"\.pdf")
                )
                if elem:
                    src = elem.get("src", "")
                    if src:
                        if not src.startswith("http"):
                            src = urljoin(base, src)
                        pdf_urls.append(
                            {
                                "url": src,
                                "pageURL": f"{base}{doi}",
                                "version": "publishedVersion",
                                "source": "scihub",
                            }
                        )
                        break

                a_tag = soup.find("a", href=re.compile(r"\.pdf"))
                if a_tag:
                    href = a_tag["href"]
                    if not href.startswith("http"):
                        href = urljoin(base, href)
                    pdf_urls.append(
                        {
                            "url": href,
                            "pageURL": f"{base}{doi}",
                            "version": "publishedVersion",
                            "source": "scihub",
                        }
                    )
                    break
            except Exception:
                continue

        self._log(f"  [Sci-Hub] 找到 {len(pdf_urls)} 个链接")
        return pdf_urls

    # -----------------------------------------------------------------
    # 来源5: 出版商网站
    # -----------------------------------------------------------------
    def get_publisher_pdf_urls(self, doi, timeout=10):
        if BeautifulSoup is None:
            self._log(f"  [出版商] 跳过 (未安装 beautifulsoup4)")
            return []

        self._log(f"  [出版商] 正在查询 …")
        doi_url = f"https://doi.org/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(doi_url, timeout=timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            pdf_urls = []

            domain = urlparse(resp.url).netloc.lower()

            if "mdpi.com" in domain:
                for link in soup.find_all("a", href=re.compile(r"/pdf$")):
                    href = link["href"]
                    if not href.startswith("http"):
                        href = urljoin(resp.url, href)
                    pdf_urls.append(
                        {
                            "url": href,
                            "pageURL": resp.url,
                            "version": "publishedVersion",
                            "source": "publisher",
                            "method": "mdpi",
                        }
                    )
                    break

            elif "sciencedirect.com" in domain:
                pii = re.search(r"/pii/([^/?]+)", resp.url)
                if pii:
                    pid = pii.group(1)
                    pdf_view = (
                        f"https://www.sciencedirect.com/science/article/pii/"
                        f"{pid}/pdfft?md5={random.randint(10**9, 10**10-1)}&pid=1-s2.0-{pid}-main.pdf"
                    )
                    pdf_urls.append(
                        {
                            "url": pdf_view,
                            "pageURL": resp.url,
                            "version": "publishedVersion",
                            "source": "publisher",
                            "method": "sciencedirect",
                        }
                    )

            else:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf"):
                        if not href.startswith("http"):
                            href = urljoin(doi_url, href)
                        pdf_urls.append(
                            {
                                "url": href,
                                "pageURL": resp.url,
                                "version": "publishedVersion",
                                "source": "publisher",
                            }
                        )
                        break

                if not pdf_urls:
                    btns = soup.find_all(
                        ["button", "a"], string=re.compile(r"download|pdf", re.I)
                    )
                    for btn in btns:
                        if btn.name == "a" and btn.get("href"):
                            href = btn["href"]
                            if not href.startswith("http"):
                                href = urljoin(doi_url, href)
                            pdf_urls.append(
                                {
                                    "url": href,
                                    "pageURL": resp.url,
                                    "version": "publishedVersion",
                                    "source": "publisher",
                                }
                            )
                            break

            self._log(f"  [出版商] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [出版商] 请求失败: {e}")
            return []

        # -----------------------------------------------------------------

    # 来源6: CORE (core.ac.uk) — 全球最大的开放获取论文聚合平台
    # -----------------------------------------------------------------
    def get_core_pdf_urls(self, doi, timeout=10):
        self._log(f"  [CORE] 正在查询 …")
        # CORE API v3 (免费，无需 API key 也可有限使用；建议申请免费 key 提高配额)
        # 如有 API key，可加 headers: {"Authorization": "Bearer YOUR_API_KEY"}
        url = f"https://api.core.ac.uk/v3/search/works/?q=doi%3A%22{doi}%22&limit=3"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for result in data.get("results", []):
                download_url = (
                    result.get("downloadUrl")
                    or result.get("sourceFulltextUrls", [None])[0]
                    if result.get("sourceFulltextUrls")
                    else None
                )
                if download_url:
                    pdf_urls.append(
                        {
                            "url": download_url,
                            "pageURL": (
                                result.get("links", [{}])[0].get("url", "")
                                if result.get("links")
                                else ""
                            ),
                            "version": "unknown",
                            "source": "core",
                        }
                    )
            self._log(f"  [CORE] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [CORE] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源7: Semantic Scholar — Allen AI 学术搜索
    # -----------------------------------------------------------------
    def get_semantic_scholar_pdf_urls(self, doi, timeout=10):
        self._log(f"  [SemanticScholar] 正在查询 …")
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=isOpenAccess,openAccessPdf"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            oa_pdf = data.get("openAccessPdf")
            if oa_pdf and oa_pdf.get("url"):
                pdf_urls.append(
                    {
                        "url": oa_pdf["url"],
                        "pageURL": f"https://www.semanticscholar.org/paper/{data.get('paperId', '')}",
                        "version": "openAccess",
                        "source": "semanticscholar",
                    }
                )
            self._log(f"  [SemanticScholar] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [SemanticScholar] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源8: OpenAlex — 开放学术图谱
    # -----------------------------------------------------------------
    def get_openalex_pdf_urls(self, doi, timeout=10):
        self._log(f"  [OpenAlex] 正在查询 …")
        url = f"https://api.openalex.org/works/doi:{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            # best_oa_location
            best_oa = data.get("best_oa_location")
            if best_oa and best_oa.get("pdf_url"):
                pdf_urls.append(
                    {
                        "url": best_oa["pdf_url"],
                        "pageURL": best_oa.get("landing_page_url", ""),
                        "version": best_oa.get("version", "unknown"),
                        "source": "openalex",
                    }
                )
            # 其他 oa_locations
            for loc in data.get("locations", []):
                if loc.get("pdf_url") and loc != best_oa:
                    pdf_urls.append(
                        {
                            "url": loc["pdf_url"],
                            "pageURL": loc.get("landing_page_url", ""),
                            "version": loc.get("version", "unknown"),
                            "source": "openalex",
                        }
                    )
            self._log(f"  [OpenAlex] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [OpenAlex] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源9: Europe PMC — 欧洲 PubMed Central
    # -----------------------------------------------------------------
    def get_europepmc_pdf_urls(self, doi, timeout=10):
        self._log(f"  [EuropePMC] 正在查询 …")
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json&resultType=core"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            results = data.get("resultList", {}).get("result", [])
            for item in results:
                pmcid = item.get("pmcid")
                if pmcid:
                    # Europe PMC 提供 OA 全文 PDF
                    pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                    pdf_urls.append(
                        {
                            "url": pdf_url,
                            "pageURL": f"https://europepmc.org/article/PMC/{pmcid}",
                            "version": "publishedVersion",
                            "source": "europepmc",
                        }
                    )
                # 也检查 fullTextUrlList
                for ft in item.get("fullTextUrlList", {}).get("fullTextUrl", []):
                    if (
                        ft.get("documentStyle") == "pdf"
                        and ft.get("availabilityCode") == "OA"
                    ):
                        pdf_urls.append(
                            {
                                "url": ft["url"],
                                "pageURL": "",
                                "version": "publishedVersion",
                                "source": "europepmc",
                            }
                        )
            self._log(f"  [EuropePMC] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [EuropePMC] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源10: PubMed Central (PMC) — NIH 开放获取
    # -----------------------------------------------------------------
    def get_pmc_pdf_urls(self, doi, timeout=10):
        self._log(f"  [PMC] 正在查询 …")
        # 先通过 NCBI ID Converter 找 PMCID
        url = (
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={doi}&format=json"
        )
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for record in data.get("records", []):
                pmcid = record.get("pmcid")
                if pmcid:
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                    pdf_urls.append(
                        {
                            "url": pdf_url,
                            "pageURL": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
                            "version": "publishedVersion",
                            "source": "pmc",
                        }
                    )
            self._log(f"  [PMC] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [PMC] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源11: DOAJ (Directory of Open Access Journals)
    # -----------------------------------------------------------------
    def get_doaj_pdf_urls(self, doi, timeout=10):
        self._log(f"  [DOAJ] 正在查询 …")
        url = f"https://doaj.org/api/search/articles/doi:{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for result in data.get("results", []):
                bibjson = result.get("bibjson", {})
                for link in bibjson.get("link", []):
                    if link.get("type") == "fulltext":
                        link_url = link.get("url", "")
                        if link_url:
                            pdf_urls.append(
                                {
                                    "url": link_url,
                                    "pageURL": link_url,
                                    "version": "publishedVersion",
                                    "source": "doaj",
                                }
                            )
            self._log(f"  [DOAJ] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [DOAJ] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源12: BASE (Bielefeld Academic Search Engine)
    # -----------------------------------------------------------------
    def get_base_pdf_urls(self, doi, timeout=10):
        self._log(f"  [BASE] 正在查询 …")
        url = f"https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi?func=PerformSearch&query=dcdoi:{doi}&format=json&hits=3"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            response = data.get("response", {})
            docs = response.get("docs", [])
            for doc in docs:
                # dclink 通常是全文链接
                links = doc.get("dclink", [])
                if isinstance(links, str):
                    links = [links]
                for lk in links:
                    if lk:
                        pdf_urls.append(
                            {
                                "url": lk,
                                "pageURL": lk,
                                "version": doc.get("dcoa", "unknown"),
                                "source": "base",
                            }
                        )
                # dcidentifier 中可能有直接 PDF 链接
                identifiers = doc.get("dcidentifier", [])
                if isinstance(identifiers, str):
                    identifiers = [identifiers]
                for ident in identifiers:
                    if isinstance(ident, str) and ident.lower().endswith(".pdf"):
                        pdf_urls.append(
                            {
                                "url": ident,
                                "pageURL": "",
                                "version": "unknown",
                                "source": "base",
                            }
                        )
            self._log(f"  [BASE] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [BASE] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源13: arXiv (适用于预印本)
    # -----------------------------------------------------------------
    def get_arxiv_pdf_urls(self, doi, timeout=10):
        self._log(f"  [arXiv] 正在查询 …")
        # arXiv API 支持通过 DOI 搜索
        url = f"http://export.arxiv.org/api/query?search_query=doi:{doi}&max_results=1"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            pdf_urls = []

            if BeautifulSoup is not None:
                soup = BeautifulSoup(resp.text, "xml")
                entries = soup.find_all("entry")
                for entry in entries:
                    arxiv_id = entry.find("id")
                    if arxiv_id:
                        aid = arxiv_id.text.strip()
                        # 将 abs 链接转为 pdf 链接
                        pdf_link = aid.replace("/abs/", "/pdf/")
                        if not pdf_link.endswith(".pdf"):
                            pdf_link += ".pdf"
                        pdf_urls.append(
                            {
                                "url": pdf_link,
                                "pageURL": aid,
                                "version": "submittedVersion",
                                "source": "arxiv",
                            }
                        )
            else:
                # 简单正则匹配
                import re as _re

                ids = _re.findall(
                    r"<id>(http://arxiv\.org/abs/[\d.]+v?\d*)</id>", resp.text
                )
                for aid in ids:
                    pdf_link = aid.replace("/abs/", "/pdf/") + ".pdf"
                    pdf_urls.append(
                        {
                            "url": pdf_link,
                            "pageURL": aid,
                            "version": "submittedVersion",
                            "source": "arxiv",
                        }
                    )

            self._log(f"  [arXiv] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [arXiv] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 处理单个 DOI (汇总所有来源)
    # -----------------------------------------------------------------
    def _process_single_doi(self, doi):
        """处理单个DOI, 依次尝试各来源, 找到即停"""
        cleaned = self.clean_doi(doi)
        if not cleaned:
            return {
                "doi": doi,
                "success": False,
                "links": [],
                "error": "无效的DOI",
                "metadata": {
                    "doi": doi,
                    "title": "未知标题",
                    "journal": "",
                    "year": "",
                    "authors": [],
                },
            }

        self._log(f"\n{'─'*60}")
        self._log(f"DOI: {cleaned}")

        metadata = self.get_article_metadata(cleaned) or {
            "doi": cleaned,
            "title": "未知标题",
            "journal": "",
            "year": "",
            "authors": [],
        }
        self._log(f"  标题: {metadata.get('title', '')}")

        # 依次查询各来源
        sources = [
            ("openaccess", self.get_open_access_pdf_urls),
            ("unpaywall", self.get_unpaywall_pdf_urls),
            ("crossref", self.get_crossref_pdf_urls),
            ("scihub", self.get_scihub_pdf_urls),
            ("publisher", self.get_publisher_pdf_urls),
            ("core", self.get_core_pdf_urls),
            ("semanticscholar", self.get_semantic_scholar_pdf_urls),
            ("openalex", self.get_openalex_pdf_urls),
            ("europepmc", self.get_europepmc_pdf_urls),
            ("pmc", self.get_pmc_pdf_urls),
            ("doaj", self.get_doaj_pdf_urls),
            ("base", self.get_base_pdf_urls),
            ("arxiv", self.get_arxiv_pdf_urls),
        ]

        all_links = []
        found_pdf = False

        for name, func in sources:
            if found_pdf:
                break
            try:
                urls = func(cleaned)
                for info in urls:
                    if isinstance(info, dict) and "url" in info:
                        link = {
                            "url": info["url"],
                            "source": info.get("source", name),
                            "version": info.get("version", "unknown"),
                            "pageURL": info.get("pageURL", ""),
                        }
                        all_links.append(link)
                        # 如果链接以 .pdf 结尾, 认为高可信度, 立即停止
                        if info["url"].lower().endswith(".pdf"):
                            found_pdf = True
                            self._log(f"  ✓ 找到 .pdf 链接 ({name}), 停止后续查询")
                            break
            except Exception as e:
                self._log(f"  [{name}] 出错: {e}")

        # 去重
        seen = set()
        unique = []
        for lk in all_links:
            if lk["url"] not in seen:
                seen.add(lk["url"])
                unique.append(lk)

        if unique:
            self._log(f"  ★ 共找到 {len(unique)} 个PDF链接")
        else:
            self._log(f"  ✗ 未找到PDF链接")

        return {
            "doi": cleaned,
            "success": len(unique) > 0,
            "links": unique,
            "metadata": metadata,
        }

    # -----------------------------------------------------------------
    # 多线程批量处理
    # -----------------------------------------------------------------
    def batch_get_pdf_links(self, doi_list, output_file, max_workers=5):
        """
        多线程批量获取 PDF 链接并写入 txt 文件

        参数:
            doi_list   : DOI 字符串列表
            output_file: 输出 txt 文件路径
            max_workers: 并发线程数 (默认 5)
        """
        # 确保输出目录存在
        out_dir = os.path.dirname(output_file)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        total = len(doi_list)
        print(f"\n{'='*60}")
        print(f"  批量PDF链接获取")
        print(f"  DOI总数   : {total}")
        print(f"  并发线程  : {max_workers}")
        print(f"  输出文件  : {output_file}")
        print(f"{'='*60}")

        stats = {"success": 0, "fail": 0, "total_links": 0}
        all_results = [None] * total  # 按原始顺序保存结果
        write_lock = threading.Lock()
        progress_lock = threading.Lock()
        finished = [0]

        def worker(index, doi):
            result = self._process_single_doi(doi)
            with progress_lock:
                finished[0] += 1
                pct = finished[0] / total * 100
                tag = "✓" if result["success"] else "✗"
                links_n = len(result["links"])
                print(
                    f"  [{finished[0]:>{len(str(total))}}/{total}] {pct:5.1f}%  {tag}  {result['doi']}  ({links_n} 链接)"
                )
            return index, result

        # 线程池执行
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(worker, i, doi): i for i, doi in enumerate(doi_list)}
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    all_results[idx] = result
                    if result["success"]:
                        stats["success"] += 1
                        stats["total_links"] += len(result["links"])
                    else:
                        stats["fail"] += 1
                except Exception as e:
                    idx = futures[future]
                    stats["fail"] += 1
                    all_results[idx] = {
                        "doi": doi_list[idx],
                        "success": False,
                        "links": [],
                        "error": str(e),
                        "metadata": {
                            "doi": doi_list[idx],
                            "title": "未知标题",
                            "journal": "",
                            "year": "",
                            "authors": [],
                        },
                    }

        # ----- 按原始顺序写入文件 -----
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("批量 PDF 下载链接获取结果\n")
            f.write(f"获取时间 : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"DOI 总数 : {total}\n")
            f.write(f"并发线程 : {max_workers}\n")
            f.write("=" * 80 + "\n\n")

            for result in all_results:
                if result is None:
                    continue
                meta = result["metadata"]
                f.write(f"DOI: {result['doi']}\n")
                f.write(f"标题: {meta.get('title', '未知标题')}\n")
                f.write(f"期刊: {meta.get('journal', '未知期刊')}\n")
                f.write(f"年份: {meta.get('year', '未知年份')}\n")
                authors = meta.get("authors", [])
                if authors:
                    f.write(f"作者: {', '.join(authors)}\n")
                f.write("-" * 80 + "\n")

                if result["links"]:
                    f.write(f"找到 {len(result['links'])} 个 PDF 下载链接:\n")
                    for i, lk in enumerate(result["links"], 1):
                        f.write(f"  {i}. 来源  : {lk['source']}\n")
                        f.write(f"     版本  : {lk['version']}\n")
                        f.write(f"     链接  : {lk['url']}\n")
                        if lk.get("pageURL"):
                            f.write(f"     页面URL: {lk['pageURL']}\n")
                else:
                    err = result.get("error", "")
                    if err:
                        f.write(f"未找到 PDF 下载链接 (原因: {err})\n")
                    else:
                        f.write("未找到 PDF 下载链接\n")
                f.write("-" * 80 + "\n\n")

            # 摘要
            f.write("=" * 80 + "\n")
            f.write("摘 要\n")
            f.write(f"  DOI 总数          : {total}\n")
            f.write(f"  成功获取链接      : {stats['success']}\n")
            f.write(f"  未找到链接        : {stats['fail']}\n")
            f.write(f"  找到的总链接数    : {stats['total_links']}\n")
            f.write("=" * 80 + "\n")

        # 终端摘要
        print(f"\n{'='*60}")
        print(f"  完成!")
        print(f"  成功 : {stats['success']} / {total}")
        print(f"  失败 : {stats['fail']} / {total}")
        print(f"  链接 : {stats['total_links']}")
        print(f"  文件 : {output_file}")
        print(f"{'='*60}\n")

        return stats


# =============================================================================
# 读取 DOI 列表
# =============================================================================
def read_doi_file(filepath):
    """
    从 txt 文件读取 DOI 列表
    支持: 每行一个 DOI, 或逗号/分号分隔
    自动跳过空行和注释行 (以 # 开头)
    """
    if not os.path.isfile(filepath):
        print(f"错误: 文件不存在 -> {filepath}")
        sys.exit(1)

    doi_list = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持逗号、分号、空格分隔
            for part in re.split(r"[,;\s]+", line):
                part = part.strip()
                if part:
                    doi_list.append(part)

    return doi_list


# =============================================================================
# 主入口
# =============================================================================
def main():
    DIR = os.getcwd()
    print(f"当前目录: {DIR}")
    Py_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"当前python目录: {Py_DIR}")
    doi_file = os.path.join(Py_DIR, "step1_all_list_doi.txt")
    output_file = os.path.join(Py_DIR, "step2_batch_pdf_links.txt")
    max_workers = 5

    # ---- 读取 DOI 列表 ----
    doi_list = read_doi_file(doi_file)

    if not doi_list:
        print("错误: 文件中未找到有效的 DOI")
        sys.exit(1)

    print(f"从 {doi_file} 读取到 {len(doi_list)} 个 DOI")

    # ---- 执行批量获取 ----
    finder = PDFLinkFinder(output_dir=os.path.dirname(output_file) or ".")
    stats = finder.batch_get_pdf_links(doi_list, output_file, max_workers=max_workers)

    # 退出码: 全部失败返回 1
    if stats["success"] == 0 and len(doi_list) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
=======
# =============================================================================
# SCI文献PDF下载链接获取工具
# 用法: python doi_pdf_finder.py doi_list.txt batch_pdf_links.txt
# 参数1: 包含DOI列表的txt文件路径 (每行一个DOI)
# 参数2: 输出文件路径 (默认: batch_pdf_links.txt)
# =============================================================================

import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    print("警告: 未安装beautifulsoup4, 部分功能(出版商/Sci-Hub)将不可用")
    print("安装方法: pip install beautifulsoup4")


# =============================================================================
# PDFLinkFinder 核心类
# =============================================================================
class PDFLinkFinder:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        self.session = requests.Session()

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0",
        ]

        self.session.headers.update(
            {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
                "DNT": "1",
                "Sec-Fetch-User": "?1",
                "Sec-Ch-Ua": '"Chromium";v="94", " Not;A Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )

        self.session.cookies.update(
            {
                "cookie_consent": "true",
                "gdpr": "1",
            }
        )

        os.makedirs(self.output_dir, exist_ok=True)
        self.cancel_download = False
        self.min_delay = 1
        self.max_delay = 3
        self.last_request_time = 0

    # -----------------------------------------------------------------
    # 内部工具方法
    # -----------------------------------------------------------------
    @staticmethod
    def _log(message):
        print(message)

    def _delay_request(self):
        """请求间随机延迟, 防止封禁"""
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()

    def _rotate_ua(self):
        """随机更换 User-Agent"""
        self.session.headers.update({"User-Agent": random.choice(self.user_agents)})

    # -----------------------------------------------------------------
    # DOI 清洗
    # -----------------------------------------------------------------
    def clean_doi(self, doi):
        if not doi:
            return None
        doi = doi.strip()
        if doi.startswith("http"):
            if "doi.org/" in doi:
                doi = doi.split("doi.org/")[-1]
            elif "/doi/" in doi:
                doi = doi.split("/doi/")[-1]
                doi = doi.split("?")[0]
        match = re.match(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", doi, re.IGNORECASE)
        return match.group(0) if match else None

    # -----------------------------------------------------------------
    # 元数据获取 (Crossref)
    # -----------------------------------------------------------------
    def get_article_metadata(self, doi, timeout=10):
        api_url = f"https://api.crossref.org/works/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(api_url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "ok":
                return None
            item = data.get("message", {})
            title = item.get("title", ["未知标题"])[0]
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}"
                for a in item.get("author", [])
            ]
            journal = item.get("container-title", ["未知期刊"])
            journal = journal[0] if journal else "未知期刊"
            date_parts = item.get(
                "published-print", item.get("published-online", {})
            ).get("date-parts", [[""]])
            year = date_parts[0][0] if date_parts and date_parts[0] else ""
            return {
                "doi": doi,
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
            }
        except Exception as e:
            self._log(f"  [元数据] 获取失败: {e}")
            return None

    # -----------------------------------------------------------------
    # 来源1: Zotero Open Access
    # -----------------------------------------------------------------
    def get_open_access_pdf_urls(self, doi, timeout=10):
        self._log(f"  [OA] 正在查询 Zotero OA …")
        url = "https://services.zotero.org/oa/search"
        try:
            self._delay_request()
            self._rotate_ua()
            self.session.headers.update(
                {
                    "Referer": "https://www.zotero.org/",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Origin": "https://www.zotero.org",
                }
            )
            resp = self.session.post(
                url,
                data=json.dumps({"doi": doi}),
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
            urls = []
            for item in raw:
                if isinstance(item, str):
                    urls.append(
                        {
                            "url": item,
                            "pageURL": "",
                            "version": "publishedVersion",
                            "source": "openaccess",
                        }
                    )
                elif isinstance(item, dict) and "url" in item:
                    item.setdefault("source", "openaccess")
                    urls.append(item)
            self._log(f"  [OA] 找到 {len(urls)} 个链接")
            return urls
        except Exception as e:
            self._log(f"  [OA] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源2: Unpaywall
    # -----------------------------------------------------------------
    def get_unpaywall_pdf_urls(self, doi, timeout=10):
        self._log(f"  [Unpaywall] 正在查询 …")
        url = f"https://api.unpaywall.org/v2/{doi}?email=postinbing@outlook.com"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            if data.get("is_oa"):
                best = data.get("best_oa_location")
                if best and best.get("url_for_pdf"):
                    pdf_urls.append(
                        {
                            "url": best["url_for_pdf"],
                            "pageURL": best.get("url", ""),
                            "version": best.get("version", "unknown"),
                            "source": "unpaywall",
                        }
                    )
                for loc in data.get("oa_locations", []):
                    if loc.get("url_for_pdf") and loc != best:
                        pdf_urls.append(
                            {
                                "url": loc["url_for_pdf"],
                                "pageURL": loc.get("url", ""),
                                "version": loc.get("version", "unknown"),
                                "source": "unpaywall",
                            }
                        )
            self._log(f"  [Unpaywall] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [Unpaywall] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源3: Crossref
    # -----------------------------------------------------------------
    def get_crossref_pdf_urls(self, doi, timeout=10):
        self._log(f"  [Crossref] 正在查询 …")
        url = f"https://api.crossref.org/works/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            if data.get("status") == "ok":
                for link in data.get("message", {}).get("link", []):
                    if "application/pdf" in link.get("content-type", ""):
                        pdf_urls.append(
                            {
                                "url": link.get("URL", ""),
                                "pageURL": "",
                                "version": "publishedVersion",
                                "source": "crossref",
                            }
                        )
            self._log(f"  [Crossref] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [Crossref] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源4: Sci-Hub
    # -----------------------------------------------------------------
    def get_scihub_pdf_urls(self, doi, timeout=10):
        if BeautifulSoup is None:
            self._log(f"  [Sci-Hub] 跳过 (未安装 beautifulsoup4)")
            return []

        self._log(f"  [Sci-Hub] 正在查询 …")
        mirrors = [
            "https://sci-hub.se/",
            "https://sci-hub.st/",
            "https://sci-hub.ru/",
            "https://sci-hub.box/",
            "https://sci-hub.red/",
            "https://sci-hub.ren/",
            "https://sci-hub.ee/",
            "https://sci-hub.wf/",
        ]
        random.shuffle(mirrors)
        pdf_urls = []

        for base in mirrors:
            try:
                self._delay_request()
                self._rotate_ua()
                self.session.headers.update({"Referer": base})
                resp = self.session.get(f"{base}{doi}", timeout=timeout)
                if resp.status_code == 403:
                    continue
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                elem = soup.find("embed", type="application/pdf") or soup.find(
                    "iframe", src=re.compile(r"\.pdf")
                )
                if elem:
                    src = elem.get("src", "")
                    if src:
                        if not src.startswith("http"):
                            src = urljoin(base, src)
                        pdf_urls.append(
                            {
                                "url": src,
                                "pageURL": f"{base}{doi}",
                                "version": "publishedVersion",
                                "source": "scihub",
                            }
                        )
                        break

                a_tag = soup.find("a", href=re.compile(r"\.pdf"))
                if a_tag:
                    href = a_tag["href"]
                    if not href.startswith("http"):
                        href = urljoin(base, href)
                    pdf_urls.append(
                        {
                            "url": href,
                            "pageURL": f"{base}{doi}",
                            "version": "publishedVersion",
                            "source": "scihub",
                        }
                    )
                    break
            except Exception:
                continue

        self._log(f"  [Sci-Hub] 找到 {len(pdf_urls)} 个链接")
        return pdf_urls

    # -----------------------------------------------------------------
    # 来源5: 出版商网站
    # -----------------------------------------------------------------
    def get_publisher_pdf_urls(self, doi, timeout=10):
        if BeautifulSoup is None:
            self._log(f"  [出版商] 跳过 (未安装 beautifulsoup4)")
            return []

        self._log(f"  [出版商] 正在查询 …")
        doi_url = f"https://doi.org/{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(doi_url, timeout=timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            pdf_urls = []

            domain = urlparse(resp.url).netloc.lower()

            if "mdpi.com" in domain:
                for link in soup.find_all("a", href=re.compile(r"/pdf$")):
                    href = link["href"]
                    if not href.startswith("http"):
                        href = urljoin(resp.url, href)
                    pdf_urls.append(
                        {
                            "url": href,
                            "pageURL": resp.url,
                            "version": "publishedVersion",
                            "source": "publisher",
                            "method": "mdpi",
                        }
                    )
                    break

            elif "sciencedirect.com" in domain:
                pii = re.search(r"/pii/([^/?]+)", resp.url)
                if pii:
                    pid = pii.group(1)
                    pdf_view = (
                        f"https://www.sciencedirect.com/science/article/pii/"
                        f"{pid}/pdfft?md5={random.randint(10**9, 10**10-1)}&pid=1-s2.0-{pid}-main.pdf"
                    )
                    pdf_urls.append(
                        {
                            "url": pdf_view,
                            "pageURL": resp.url,
                            "version": "publishedVersion",
                            "source": "publisher",
                            "method": "sciencedirect",
                        }
                    )

            else:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf"):
                        if not href.startswith("http"):
                            href = urljoin(doi_url, href)
                        pdf_urls.append(
                            {
                                "url": href,
                                "pageURL": resp.url,
                                "version": "publishedVersion",
                                "source": "publisher",
                            }
                        )
                        break

                if not pdf_urls:
                    btns = soup.find_all(
                        ["button", "a"], string=re.compile(r"download|pdf", re.I)
                    )
                    for btn in btns:
                        if btn.name == "a" and btn.get("href"):
                            href = btn["href"]
                            if not href.startswith("http"):
                                href = urljoin(doi_url, href)
                            pdf_urls.append(
                                {
                                    "url": href,
                                    "pageURL": resp.url,
                                    "version": "publishedVersion",
                                    "source": "publisher",
                                }
                            )
                            break

            self._log(f"  [出版商] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [出版商] 请求失败: {e}")
            return []

        # -----------------------------------------------------------------

    # 来源6: CORE (core.ac.uk) — 全球最大的开放获取论文聚合平台
    # -----------------------------------------------------------------
    def get_core_pdf_urls(self, doi, timeout=10):
        self._log(f"  [CORE] 正在查询 …")
        # CORE API v3 (免费，无需 API key 也可有限使用；建议申请免费 key 提高配额)
        # 如有 API key，可加 headers: {"Authorization": "Bearer YOUR_API_KEY"}
        url = f"https://api.core.ac.uk/v3/search/works/?q=doi%3A%22{doi}%22&limit=3"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for result in data.get("results", []):
                download_url = (
                    result.get("downloadUrl")
                    or result.get("sourceFulltextUrls", [None])[0]
                    if result.get("sourceFulltextUrls")
                    else None
                )
                if download_url:
                    pdf_urls.append(
                        {
                            "url": download_url,
                            "pageURL": (
                                result.get("links", [{}])[0].get("url", "")
                                if result.get("links")
                                else ""
                            ),
                            "version": "unknown",
                            "source": "core",
                        }
                    )
            self._log(f"  [CORE] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [CORE] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源7: Semantic Scholar — Allen AI 学术搜索
    # -----------------------------------------------------------------
    def get_semantic_scholar_pdf_urls(self, doi, timeout=10):
        self._log(f"  [SemanticScholar] 正在查询 …")
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=isOpenAccess,openAccessPdf"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            oa_pdf = data.get("openAccessPdf")
            if oa_pdf and oa_pdf.get("url"):
                pdf_urls.append(
                    {
                        "url": oa_pdf["url"],
                        "pageURL": f"https://www.semanticscholar.org/paper/{data.get('paperId', '')}",
                        "version": "openAccess",
                        "source": "semanticscholar",
                    }
                )
            self._log(f"  [SemanticScholar] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [SemanticScholar] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源8: OpenAlex — 开放学术图谱
    # -----------------------------------------------------------------
    def get_openalex_pdf_urls(self, doi, timeout=10):
        self._log(f"  [OpenAlex] 正在查询 …")
        url = f"https://api.openalex.org/works/doi:{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            # best_oa_location
            best_oa = data.get("best_oa_location")
            if best_oa and best_oa.get("pdf_url"):
                pdf_urls.append(
                    {
                        "url": best_oa["pdf_url"],
                        "pageURL": best_oa.get("landing_page_url", ""),
                        "version": best_oa.get("version", "unknown"),
                        "source": "openalex",
                    }
                )
            # 其他 oa_locations
            for loc in data.get("locations", []):
                if loc.get("pdf_url") and loc != best_oa:
                    pdf_urls.append(
                        {
                            "url": loc["pdf_url"],
                            "pageURL": loc.get("landing_page_url", ""),
                            "version": loc.get("version", "unknown"),
                            "source": "openalex",
                        }
                    )
            self._log(f"  [OpenAlex] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [OpenAlex] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源9: Europe PMC — 欧洲 PubMed Central
    # -----------------------------------------------------------------
    def get_europepmc_pdf_urls(self, doi, timeout=10):
        self._log(f"  [EuropePMC] 正在查询 …")
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json&resultType=core"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            results = data.get("resultList", {}).get("result", [])
            for item in results:
                pmcid = item.get("pmcid")
                if pmcid:
                    # Europe PMC 提供 OA 全文 PDF
                    pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                    pdf_urls.append(
                        {
                            "url": pdf_url,
                            "pageURL": f"https://europepmc.org/article/PMC/{pmcid}",
                            "version": "publishedVersion",
                            "source": "europepmc",
                        }
                    )
                # 也检查 fullTextUrlList
                for ft in item.get("fullTextUrlList", {}).get("fullTextUrl", []):
                    if (
                        ft.get("documentStyle") == "pdf"
                        and ft.get("availabilityCode") == "OA"
                    ):
                        pdf_urls.append(
                            {
                                "url": ft["url"],
                                "pageURL": "",
                                "version": "publishedVersion",
                                "source": "europepmc",
                            }
                        )
            self._log(f"  [EuropePMC] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [EuropePMC] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源10: PubMed Central (PMC) — NIH 开放获取
    # -----------------------------------------------------------------
    def get_pmc_pdf_urls(self, doi, timeout=10):
        self._log(f"  [PMC] 正在查询 …")
        # 先通过 NCBI ID Converter 找 PMCID
        url = (
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={doi}&format=json"
        )
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for record in data.get("records", []):
                pmcid = record.get("pmcid")
                if pmcid:
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                    pdf_urls.append(
                        {
                            "url": pdf_url,
                            "pageURL": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
                            "version": "publishedVersion",
                            "source": "pmc",
                        }
                    )
            self._log(f"  [PMC] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [PMC] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源11: DOAJ (Directory of Open Access Journals)
    # -----------------------------------------------------------------
    def get_doaj_pdf_urls(self, doi, timeout=10):
        self._log(f"  [DOAJ] 正在查询 …")
        url = f"https://doaj.org/api/search/articles/doi:{doi}"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            for result in data.get("results", []):
                bibjson = result.get("bibjson", {})
                for link in bibjson.get("link", []):
                    if link.get("type") == "fulltext":
                        link_url = link.get("url", "")
                        if link_url:
                            pdf_urls.append(
                                {
                                    "url": link_url,
                                    "pageURL": link_url,
                                    "version": "publishedVersion",
                                    "source": "doaj",
                                }
                            )
            self._log(f"  [DOAJ] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [DOAJ] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源12: BASE (Bielefeld Academic Search Engine)
    # -----------------------------------------------------------------
    def get_base_pdf_urls(self, doi, timeout=10):
        self._log(f"  [BASE] 正在查询 …")
        url = f"https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi?func=PerformSearch&query=dcdoi:{doi}&format=json&hits=3"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            pdf_urls = []
            response = data.get("response", {})
            docs = response.get("docs", [])
            for doc in docs:
                # dclink 通常是全文链接
                links = doc.get("dclink", [])
                if isinstance(links, str):
                    links = [links]
                for lk in links:
                    if lk:
                        pdf_urls.append(
                            {
                                "url": lk,
                                "pageURL": lk,
                                "version": doc.get("dcoa", "unknown"),
                                "source": "base",
                            }
                        )
                # dcidentifier 中可能有直接 PDF 链接
                identifiers = doc.get("dcidentifier", [])
                if isinstance(identifiers, str):
                    identifiers = [identifiers]
                for ident in identifiers:
                    if isinstance(ident, str) and ident.lower().endswith(".pdf"):
                        pdf_urls.append(
                            {
                                "url": ident,
                                "pageURL": "",
                                "version": "unknown",
                                "source": "base",
                            }
                        )
            self._log(f"  [BASE] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [BASE] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 来源13: arXiv (适用于预印本)
    # -----------------------------------------------------------------
    def get_arxiv_pdf_urls(self, doi, timeout=10):
        self._log(f"  [arXiv] 正在查询 …")
        # arXiv API 支持通过 DOI 搜索
        url = f"http://export.arxiv.org/api/query?search_query=doi:{doi}&max_results=1"
        try:
            self._delay_request()
            self._rotate_ua()
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            pdf_urls = []

            if BeautifulSoup is not None:
                soup = BeautifulSoup(resp.text, "xml")
                entries = soup.find_all("entry")
                for entry in entries:
                    arxiv_id = entry.find("id")
                    if arxiv_id:
                        aid = arxiv_id.text.strip()
                        # 将 abs 链接转为 pdf 链接
                        pdf_link = aid.replace("/abs/", "/pdf/")
                        if not pdf_link.endswith(".pdf"):
                            pdf_link += ".pdf"
                        pdf_urls.append(
                            {
                                "url": pdf_link,
                                "pageURL": aid,
                                "version": "submittedVersion",
                                "source": "arxiv",
                            }
                        )
            else:
                # 简单正则匹配
                import re as _re

                ids = _re.findall(
                    r"<id>(http://arxiv\.org/abs/[\d.]+v?\d*)</id>", resp.text
                )
                for aid in ids:
                    pdf_link = aid.replace("/abs/", "/pdf/") + ".pdf"
                    pdf_urls.append(
                        {
                            "url": pdf_link,
                            "pageURL": aid,
                            "version": "submittedVersion",
                            "source": "arxiv",
                        }
                    )

            self._log(f"  [arXiv] 找到 {len(pdf_urls)} 个链接")
            return pdf_urls
        except Exception as e:
            self._log(f"  [arXiv] 请求失败: {e}")
            return []

    # -----------------------------------------------------------------
    # 处理单个 DOI (汇总所有来源)
    # -----------------------------------------------------------------
    def _process_single_doi(self, doi):
        """处理单个DOI, 依次尝试各来源, 找到即停"""
        cleaned = self.clean_doi(doi)
        if not cleaned:
            return {
                "doi": doi,
                "success": False,
                "links": [],
                "error": "无效的DOI",
                "metadata": {
                    "doi": doi,
                    "title": "未知标题",
                    "journal": "",
                    "year": "",
                    "authors": [],
                },
            }

        self._log(f"\n{'─'*60}")
        self._log(f"DOI: {cleaned}")

        metadata = self.get_article_metadata(cleaned) or {
            "doi": cleaned,
            "title": "未知标题",
            "journal": "",
            "year": "",
            "authors": [],
        }
        self._log(f"  标题: {metadata.get('title', '')}")

        # 依次查询各来源
        sources = [
            ("openaccess", self.get_open_access_pdf_urls),
            ("unpaywall", self.get_unpaywall_pdf_urls),
            ("crossref", self.get_crossref_pdf_urls),
            ("scihub", self.get_scihub_pdf_urls),
            ("publisher", self.get_publisher_pdf_urls),
            ("core", self.get_core_pdf_urls),
            ("semanticscholar", self.get_semantic_scholar_pdf_urls),
            ("openalex", self.get_openalex_pdf_urls),
            ("europepmc", self.get_europepmc_pdf_urls),
            ("pmc", self.get_pmc_pdf_urls),
            ("doaj", self.get_doaj_pdf_urls),
            ("base", self.get_base_pdf_urls),
            ("arxiv", self.get_arxiv_pdf_urls),
        ]

        all_links = []
        found_pdf = False

        for name, func in sources:
            if found_pdf:
                break
            try:
                urls = func(cleaned)
                for info in urls:
                    if isinstance(info, dict) and "url" in info:
                        link = {
                            "url": info["url"],
                            "source": info.get("source", name),
                            "version": info.get("version", "unknown"),
                            "pageURL": info.get("pageURL", ""),
                        }
                        all_links.append(link)
                        # 如果链接以 .pdf 结尾, 认为高可信度, 立即停止
                        if info["url"].lower().endswith(".pdf"):
                            found_pdf = True
                            self._log(f"  ✓ 找到 .pdf 链接 ({name}), 停止后续查询")
                            break
            except Exception as e:
                self._log(f"  [{name}] 出错: {e}")

        # 去重
        seen = set()
        unique = []
        for lk in all_links:
            if lk["url"] not in seen:
                seen.add(lk["url"])
                unique.append(lk)

        if unique:
            self._log(f"  ★ 共找到 {len(unique)} 个PDF链接")
        else:
            self._log(f"  ✗ 未找到PDF链接")

        return {
            "doi": cleaned,
            "success": len(unique) > 0,
            "links": unique,
            "metadata": metadata,
        }

    # -----------------------------------------------------------------
    # 多线程批量处理
    # -----------------------------------------------------------------
    def batch_get_pdf_links(self, doi_list, output_file, max_workers=5):
        """
        多线程批量获取 PDF 链接并写入 txt 文件

        参数:
            doi_list   : DOI 字符串列表
            output_file: 输出 txt 文件路径
            max_workers: 并发线程数 (默认 5)
        """
        # 确保输出目录存在
        out_dir = os.path.dirname(output_file)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        total = len(doi_list)
        print(f"\n{'='*60}")
        print(f"  批量PDF链接获取")
        print(f"  DOI总数   : {total}")
        print(f"  并发线程  : {max_workers}")
        print(f"  输出文件  : {output_file}")
        print(f"{'='*60}")

        stats = {"success": 0, "fail": 0, "total_links": 0}
        all_results = [None] * total  # 按原始顺序保存结果
        write_lock = threading.Lock()
        progress_lock = threading.Lock()
        finished = [0]

        def worker(index, doi):
            result = self._process_single_doi(doi)
            with progress_lock:
                finished[0] += 1
                pct = finished[0] / total * 100
                tag = "✓" if result["success"] else "✗"
                links_n = len(result["links"])
                print(
                    f"  [{finished[0]:>{len(str(total))}}/{total}] {pct:5.1f}%  {tag}  {result['doi']}  ({links_n} 链接)"
                )
            return index, result

        # 线程池执行
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(worker, i, doi): i for i, doi in enumerate(doi_list)}
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    all_results[idx] = result
                    if result["success"]:
                        stats["success"] += 1
                        stats["total_links"] += len(result["links"])
                    else:
                        stats["fail"] += 1
                except Exception as e:
                    idx = futures[future]
                    stats["fail"] += 1
                    all_results[idx] = {
                        "doi": doi_list[idx],
                        "success": False,
                        "links": [],
                        "error": str(e),
                        "metadata": {
                            "doi": doi_list[idx],
                            "title": "未知标题",
                            "journal": "",
                            "year": "",
                            "authors": [],
                        },
                    }

        # ----- 按原始顺序写入文件 -----
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("批量 PDF 下载链接获取结果\n")
            f.write(f"获取时间 : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"DOI 总数 : {total}\n")
            f.write(f"并发线程 : {max_workers}\n")
            f.write("=" * 80 + "\n\n")

            for result in all_results:
                if result is None:
                    continue
                meta = result["metadata"]
                f.write(f"DOI: {result['doi']}\n")
                f.write(f"标题: {meta.get('title', '未知标题')}\n")
                f.write(f"期刊: {meta.get('journal', '未知期刊')}\n")
                f.write(f"年份: {meta.get('year', '未知年份')}\n")
                authors = meta.get("authors", [])
                if authors:
                    f.write(f"作者: {', '.join(authors)}\n")
                f.write("-" * 80 + "\n")

                if result["links"]:
                    f.write(f"找到 {len(result['links'])} 个 PDF 下载链接:\n")
                    for i, lk in enumerate(result["links"], 1):
                        f.write(f"  {i}. 来源  : {lk['source']}\n")
                        f.write(f"     版本  : {lk['version']}\n")
                        f.write(f"     链接  : {lk['url']}\n")
                        if lk.get("pageURL"):
                            f.write(f"     页面URL: {lk['pageURL']}\n")
                else:
                    err = result.get("error", "")
                    if err:
                        f.write(f"未找到 PDF 下载链接 (原因: {err})\n")
                    else:
                        f.write("未找到 PDF 下载链接\n")
                f.write("-" * 80 + "\n\n")

            # 摘要
            f.write("=" * 80 + "\n")
            f.write("摘 要\n")
            f.write(f"  DOI 总数          : {total}\n")
            f.write(f"  成功获取链接      : {stats['success']}\n")
            f.write(f"  未找到链接        : {stats['fail']}\n")
            f.write(f"  找到的总链接数    : {stats['total_links']}\n")
            f.write("=" * 80 + "\n")

        # 终端摘要
        print(f"\n{'='*60}")
        print(f"  完成!")
        print(f"  成功 : {stats['success']} / {total}")
        print(f"  失败 : {stats['fail']} / {total}")
        print(f"  链接 : {stats['total_links']}")
        print(f"  文件 : {output_file}")
        print(f"{'='*60}\n")

        return stats


# =============================================================================
# 读取 DOI 列表
# =============================================================================
def read_doi_file(filepath):
    """
    从 txt 文件读取 DOI 列表
    支持: 每行一个 DOI, 或逗号/分号分隔
    自动跳过空行和注释行 (以 # 开头)
    """
    if not os.path.isfile(filepath):
        print(f"错误: 文件不存在 -> {filepath}")
        sys.exit(1)

    doi_list = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持逗号、分号、空格分隔
            for part in re.split(r"[,;\s]+", line):
                part = part.strip()
                if part:
                    doi_list.append(part)

    return doi_list


# =============================================================================
# 主入口
# =============================================================================
def main():
    DIR = os.getcwd()
    print(f"当前目录: {DIR}")
    Py_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"当前python目录: {Py_DIR}")
    doi_file = os.path.join(Py_DIR, "step1_all_list_doi.txt")
    output_file = os.path.join(Py_DIR, "step2_batch_pdf_links.txt")
    max_workers = 5

    # ---- 读取 DOI 列表 ----
    doi_list = read_doi_file(doi_file)

    if not doi_list:
        print("错误: 文件中未找到有效的 DOI")
        sys.exit(1)

    print(f"从 {doi_file} 读取到 {len(doi_list)} 个 DOI")

    # ---- 执行批量获取 ----
    finder = PDFLinkFinder(output_dir=os.path.dirname(output_file) or ".")
    stats = finder.batch_get_pdf_links(doi_list, output_file, max_workers=max_workers)

    # 退出码: 全部失败返回 1
    if stats["success"] == 0 and len(doi_list) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
>>>>>>> 34a7861bfc90a87a77c760888c4582ab3bf72350
