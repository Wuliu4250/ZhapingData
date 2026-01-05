"""
智联招聘上市公司职位爬虫
使用Selenium + Chrome浏览器自动化
需要手动登录后自动爬取
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import csv
import random
from datetime import datetime
import logging
import subprocess
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zhaopin_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ZhaopinCrawler:
    def __init__(self):
        """初始化爬虫"""
        self.driver = None
        self.job_data = []
        self.wait_timeout = 10
        self.page_delay_range = (3, 6)  # 增加延迟范围，减少访问频率
        self.list_window = None  # 列表页标签页
        self.detail_window = None  # 详情页标签页

    def init_driver(self):
        """初始化Chrome浏览器驱动"""
        logger.info("正在初始化浏览器...")

        chrome_options = Options()

        # 添加用户代理，模拟真实浏览器
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # 禁用自动化检测 - 关键设置
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')

        # 移除webdriver痕迹
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--profile-directory=Default')
        chrome_options.add_argument('--disable-plugins-discovery')
        chrome_options.add_argument('--start-maximized')

        # 尝试使用已存在的用户数据目录（绕过安全验证）
        user_data_dir = os.path.join(os.getcwd(), 'chrome_user_data')
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.maximize_window()

            # 执行CDP命令移除webdriver属性
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })

            logger.info("浏览器初始化成功")
            logger.info("提示：如果出现安全验证，请在浏览器中手动完成验证")
            return True
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            logger.error("请确保已安装Chrome浏览器和ChromeDriver")
            return False
    
    def manual_login(self, url):
        """
        手动登录
        打开页面后等待用户手动登录
        """
        logger.info(f"正在打开页面: {url}")
        self.driver.get(url)

        # 记录列表页窗口句柄
        self.list_window = self.driver.current_window_handle
        logger.info(f"列表页窗口句柄: {self.list_window}")

        logger.info("=" * 60)
        logger.info("请在浏览器中完成以下步骤：")
        logger.info("1. 如果页面未登录，请点击登录按钮")
        logger.info("2. 使用您的账号密码登录")
        logger.info("3. 登录成功后，请确认页面显示的是职位列表")
        logger.info("=" * 60)

        input("登录完成后，请在控制台按 Enter 键继续...")

        # 打开一个新的标签页用于显示职位详情
        self.driver.execute_script("window.open('');")
        # 切换到新标签页
        self.detail_window = self.driver.window_handles[1]
        self.driver.switch_to.window(self.detail_window)
        logger.info(f"详情页窗口句柄: {self.detail_window}")
        logger.info(f"已创建详情页标签页，标签页数量: {len(self.driver.window_handles)}")

        # 切回列表页
        self.driver.switch_to.window(self.list_window)
        logger.info("开始爬取职位数据...")
    
    def random_delay(self):
        """随机延迟，避免请求过快"""
        delay = random.uniform(*self.page_delay_range)
        time.sleep(delay)
    
    def get_job_list_elements(self):
        """获取职位列表中的所有职位元素"""
        try:
            # 等待页面加载
            logger.info("等待职位列表加载...")
            time.sleep(3)  # 给页面足够的时间加载

            # 首先尝试找到所有职位详情页的链接
            job_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="jobdetail/"]')

            if job_links:
                logger.info(f"找到 {len(job_links)} 个职位链接")
                return job_links

            # 如果没找到，尝试其他可能的选择器
            logger.info("未找到jobdetail链接，尝试其他选择器...")

            selectors = [
                '.joblist-box .job-card-wrapper',
                '.job-list .job-item',
                '[class*="job-card"]',
                '[class*="job-item"]',
                'a[href*="/jobdetail/"]',
                'a[href*="/job/"]',
                'a[href*="zhaopin.com/"]',
            ]

            job_elements = []
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"使用选择器 '{selector}' 找到 {len(elements)} 个元素")
                        job_elements = elements
                        break
                except:
                    continue

            return job_elements

        except Exception as e:
            logger.error(f"获取职位列表失败: {e}")
            return []
    
    def extract_job_detail(self):
        """从职位详情页提取信息"""
        job_info = {
            '职位名称': '',
            '薪资': '',
            '工作地点': '',
            '公司名称': '',
            '任职要求': '',
            '学历要求': '',
            '招聘人数': '',
            '发布时间': ''
        }

        try:
            # 等待页面加载完成
            logger.info("等待详情页加载...")
            time.sleep(4)  # 给足够的时间让页面完全加载

            # 打印当前URL，确认是否在详情页
            current_url = self.driver.current_url
            logger.info(f"当前页面URL: {current_url}")

            if 'jobdetail' not in current_url:
                logger.warning("当前不在详情页！")

            # 职位名称 - 使用精确XPath
            try:
                job_title = self.driver.find_element(By.XPATH, '/html/body/div/div[4]/div[1]/div/h3').text.strip()
                if job_title and len(job_title) > 2 and len(job_title) < 100:
                    job_info['职位名称'] = job_title
                    logger.info(f"职位名称: {job_title}")
            except Exception as e:
                logger.warning(f"未找到职位名称: {e}")

            # 薪资 - 使用精确XPath
            try:
                salary = self.driver.find_element(By.XPATH, '/html/body/div/div[4]/div[1]/div/div[2]/div[1]/span').text.strip()
                if salary:
                    job_info['薪资'] = salary
                    logger.info(f"薪资: {salary}")
            except Exception as e:
                logger.warning(f"未找到薪资信息: {e}")
                job_info['薪资'] = '面议'

            # 工作地点和学历要求 - 从UL元素中提取
            try:
                # 获取包含工作地点、经验要求等的UL元素
                ul_element = self.driver.find_element(By.XPATH, '/html/body/div/div[4]/div[1]/div/div[2]/div[1]/ul')

                # 获取所有li元素
                li_elements = ul_element.find_elements(By.TAG_NAME, 'li')
                if li_elements:
                    location_text = li_elements[0].text.strip()
                    if location_text:
                        job_info['工作地点']  = location_text    
                        logger.info(f"工作地点：{location_text}")                  
                # 遍历所有li元素，提取工作地点、学历要求和招聘人数
                for li in li_elements:
                    text = li.text.strip()
                    if not text:
                        continue

                    # 检查是否包含招聘人数（格式：招×人）
                    if '招' in text and '人' in text:
                        # 提取"招"和"人"之间的数字
                        import re
                        match = re.search(r'招(\d+)人', text)
                        if match:
                            recruit_num = match.group(1)  # 只提取数字
                            job_info['招聘人数'] = recruit_num
                            logger.info(f"招聘人数: {recruit_num}")

                    # 检查是否包含学历关键字
                    education_keywords = ['大专', '本科', '硕士', '博士', '高中', '中专', '初中', '学历不限']
                    for keyword in education_keywords:
                        if keyword in text:
                            job_info['学历要求'] = text
                            logger.info(f"学历要求: {text}")
                            break


            except Exception as e:
                logger.warning(f"未找到工作地点或学历要求: {e}")

            # 公司名称 - 使用精确XPath
            try:
                company_element = self.driver.find_element(By.XPATH, '/html/body/div/div[5]/div[2]/div/div[3]/a[1]')
                company_name = company_element.text.strip()
                if company_name:
                    job_info['公司名称'] = company_name
                    logger.info(f"公司名称: {company_name}")
            except Exception as e:
                logger.warning(f"未找到公司名称: {e}")

            # 任职要求 - 使用精确XPath
            try:
                # 使用class="describtion__detail-content"来定位
                job_desc = self.driver.find_element(By.XPATH, '//div[@class="describtion__detail-content"]').text.strip()
                if job_desc and len(job_desc) > 10:
                    job_info['任职要求'] = job_desc
                    logger.info(f"任职要求: {job_desc[:50]}...")
            except Exception as e:
                logger.warning(f"未找到任职要求（使用主要选择器）: {e}")
                # 备选方案：尝试其他可能的选择器
                try:
                    job_desc = self.driver.find_element(By.CSS_SELECTOR, '.describtion__detail-content').text.strip()
                    if job_desc and len(job_desc) > 10:
                        job_info['任职要求'] = job_desc
                        logger.info(f"任职要求: {job_desc[:50]}...")
                except Exception as e2:
                    logger.warning(f"未找到任职要求（使用备选选择器）: {e2}")
                    job_info['任职要求'] = '无'

            # 发布时间 - 使用精确XPath
            try:
                publish_time = self.driver.find_element(By.XPATH, '/html/body/div/div[4]/div[1]/div/div[1]/div[1]/span').text.strip()
                if publish_time:
                    job_info['发布时间'] = publish_time
                    logger.info(f"发布时间: {publish_time}")
            except Exception as e:
                logger.warning(f"未找到发布时间: {e}")
                job_info['发布时间'] = datetime.now().strftime('%Y-%m-%d')

            # 检查是否至少提取到了一些数据
            if any(job_info.values()):
                self.job_data.append(job_info)
                logger.info(f"成功提取职位信息，当前共 {len(self.job_data)} 条")
            else:
                logger.warning("未能提取到任何职位信息")

        except Exception as e:
            logger.error(f"提取职位详情失败: {e}")
            import traceback
            traceback.print_exc()

        return job_info
    
    def go_back(self):
        """返回上一页"""
        try:
            self.driver.back()
            time.sleep(2)  # 等待页面加载
        except Exception as e:
            logger.error(f"返回失败: {e}")
    
    def click_next_page(self):
        """点击下一页"""
        try:
            # 尝试多种下一页按钮选择器
            next_selectors = [
                '.pagination .next:not(.disabled)',  # 原始选择器
                '.pagination .next',  # 不检查disabled
                '[class*="pagination"] [class*="next"]',  # 更宽松的选择器
                'a[class*="next"]',  # 备选选择器
            ]

            next_button = None
            for selector in next_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in buttons:
                        btn_text = btn.text.lower()
                        # 排除已禁用的按钮
                        if btn_text and 'next' in btn_text or '下一页' in btn.text:
                            btn_class = btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                next_button = btn
                                logger.info(f"使用选择器 '{selector}' 找到下一页按钮")
                                break
                    if next_button:
                        break
                except:
                    continue

            if next_button:
                # 滚动到按钮位置
                self.driver.execute_script("arguments[0].scrollIntoView();", next_button)
                time.sleep(1)
                next_button.click()
                self.random_delay()
                logger.info("成功点击下一页")
                return True
            else:
                logger.info("没有找到下一页按钮，可能已到最后一页")
                return False
        except Exception as e:
            logger.error(f"点击下一页失败: {e}")
            return False
    
    def crawl_page(self):
        """爬取当前页面的所有职位"""
        logger.info("=" * 60)
        logger.info("开始爬取当前页面")

        # 确保在列表页标签页
        self.driver.switch_to.window(self.list_window)

        # 先获取所有职位的URL，避免元素失效问题
        job_elements = self.get_job_list_elements()
        if not job_elements:
            logger.error("未找到任何职位元素")
            return False

        # 提前获取所有职位的URL
        job_urls = []
        for elem in job_elements:
            try:
                if elem.tag_name == 'a':
                    url = elem.get_attribute('href')
                    if url and 'jobdetail' in url:
                        job_urls.append(url)
            except:
                pass

        logger.info(f"成功提取 {len(job_urls)} 个职位URL")

        if not job_urls:
            logger.error("没有获取到任何职位URL")
            return False

        # 遍历职位URL
        for idx, job_url in enumerate(job_urls, 1):
            try:
                logger.info(f"\n正在处理第 {idx}/{len(job_urls)} 个职位")

                logger.info(f"职位URL: {job_url}")

                # 增加随机延迟，避免频繁访问
                time.sleep(random.uniform(2, 4))

                # 切换到详情页标签页
                logger.info("切换到详情页标签页...")
                self.driver.switch_to.window(self.detail_window)
                self.driver.get(job_url)

                # 等待详情页加载并验证
                time.sleep(random.uniform(3, 5))
                new_url = self.driver.current_url
                logger.info(f"详情页URL: {new_url}")

                # 检查是否进入安全验证页
                if 'verify' in new_url or 'captcha' in new_url or 'validate' in new_url:
                    logger.warning("=" * 60)
                    logger.warning("检测到安全验证页面！")
                    logger.warning("=" * 60)
                    logger.info("请在浏览器中手动完成验证（滑动、点击等）")
                    logger.info("验证完成后，请在控制台按 Enter 键继续...")
                    input()
                    new_url = self.driver.current_url
                    logger.info(f"验证后URL: {new_url}")

                if 'jobdetail' not in new_url:
                    logger.warning("警告：URL中没有'jobdetail'，可能没有成功进入详情页")
                    # 检查是否需要重新验证
                    logger.info("请在浏览器中确认页面状态，然后按 Enter 键继续...")
                    input()

                # 提取职位详情
                self.extract_job_detail()

                # 切换回列表页标签页
                logger.info("切换回列表页标签页...")
                self.driver.switch_to.window(self.list_window)
                time.sleep(random.uniform(1, 2))

            except Exception as e:
                logger.error(f"处理第 {idx} 个职位时出错: {e}")
                import traceback
                traceback.print_exc()
                # 尝试切换回列表页
                try:
                    self.driver.switch_to.window(self.list_window)
                    time.sleep(1)
                except:
                    pass
                continue

        return True
    
    def save_to_csv(self, filename):
        """保存数据到CSV文件"""
        if not self.job_data:
            logger.warning("没有数据可保存")
            return
        
        logger.info(f"正在保存数据到 {filename}...")
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['职位名称', '薪资', '工作地点', '公司名称', '任职要求', '学历要求', '招聘人数', '发布时间']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for job in self.job_data:
                writer.writerow(job)
        
        logger.info(f"成功保存 {len(self.job_data)} 条数据到 {filename}")
    
    def click_latest_publish_button(self):
        """点击'最新发布'按钮以加载职位列表"""
        # 确保在列表页标签页
        self.driver.switch_to.window(self.list_window)

        try:
            logger.info("尝试点击'最新发布'按钮...")
            latest_button = self.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/div[2]/div[1]/ul/li[3]/a')
            latest_button.click()
            time.sleep(random.uniform(2, 3))
            logger.info("成功点击'最新发布'按钮")
            return True
        except Exception as e:
            logger.warning(f"未找到或无法点击'最新发布'按钮: {e}")
            return False

    def get_page_url(self, base_url, page_num):
        """
        构造指定页码的URL
        :param base_url: 基础URL（不带页码）
        :param page_num: 页码
        :return: 完整URL
        """
        # 将URL中的pN替换为pn，例如p1替换为p2
        import re
        return re.sub(r'/p\d+', f'/p{page_num}', base_url)

    def click_page_button(self, page_num):
        """点击指定页码的按钮进行翻页"""
        # 确保在列表页标签页
        self.driver.switch_to.window(self.list_window)

        try:
            # 查找指定页码的按钮
            page_button = self.driver.find_element(By.XPATH, f'//a[contains(@class, "soupager__index") and text()="{page_num}"]')
            page_button.click()
            logger.info(f"成功点击第 {page_num} 页按钮")
            time.sleep(random.uniform(3, 5))
            return True
        except Exception as e:
            logger.warning(f"未找到或无法点击第 {page_num} 页按钮: {e}")
            return False

    def crawl(self, start_url, max_pages=None):
        """
        开始爬取
        :param start_url: 起始URL
        :param max_pages: 最大爬取页数，None表示爬取所有页
        """
        # 初始化浏览器
        if not self.init_driver():
            return False

        try:
            # 手动登录
            self.manual_login(start_url)

            # 点击"最新发布"按钮加载职位列表
            self.click_latest_publish_button()

            # 开始爬取
            page_num = 1
            save_interval = 8  # 每8页保存一次
            while True:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"正在爬取第 {page_num} 页")
                logger.info(f"{'=' * 60}")

                # 爬取当前页
                success = self.crawl_page()
                if not success:
                    break

                # 检查是否达到最大页数
                if max_pages and page_num >= max_pages:
                    logger.info(f"已达到最大页数 {max_pages}，停止爬取")
                    break

                # 每8页保存一次数据
                if page_num % save_interval == 0:
                    logger.info(f"\n已爬取 {page_num} 页，正在保存数据...")
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f'zhaopin_jobs_page{page_num}_{timestamp}.csv'
                    self.save_to_csv(filename)
                    logger.info(f"已保存到 {filename}，当前共 {len(self.job_data)} 条数据")

                # 翻页
                page_num += 1
                logger.info(f"准备翻到第 {page_num} 页...")

                # 点击下一页按钮
                if not self.click_page_button(page_num):
                    logger.info("无法找到下一页按钮，可能已到最后一页")
                    break

            # 保存数据
            if self.job_data:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'zhaopin_jobs_{timestamp}.csv'
                self.save_to_csv(filename)
            else:
                logger.warning("没有爬取到任何数据")

            logger.info(f"爬取完成！共爬取 {len(self.job_data)} 条职位信息")
            return True

        except KeyboardInterrupt:
            logger.info("\n用户中断爬取")
            if self.job_data:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'zhaopin_jobs_interrupted_{timestamp}.csv'
                self.save_to_csv(filename)
            return False
        except Exception as e:
            logger.error(f"爬取过程中出现错误: {e}")
            return False
        finally:
            # 保存数据
            if self.job_data:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'zhaopin_jobs_{timestamp}.csv'
                self.save_to_csv(filename)

            # 关闭浏览器
            if self.driver:
                logger.info("正在关闭浏览器...")
                self.driver.quit()


def main():
    """主函数"""
    # 目标URL - 智联招聘上市公司职位
    target_url = "https://www.zhaopin.com/sou/jl489/p1?ct=9"
    
    # 创建爬虫实例
    crawler = ZhaopinCrawler()
    
    # 开始爬取
    # max_pages: 设置爬取的最大页数，例如3表示只爬取3页
    # 设置为None表示爬取所有页面
    max_pages = None  # 可以改为具体数字，如 3, 5, 10 等
    
    logger.info("开始爬取智联招聘上市公司职位数据...")
    crawler.crawl(target_url, max_pages=max_pages)
    
    logger.info("程序执行完毕")


if __name__ == '__main__':
    main()
