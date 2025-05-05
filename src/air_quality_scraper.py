"""
空气质量数据爬虫模块

这个模块负责从空气质量监测网站爬取历史数据。
主要功能包括：
1. 爬取指定日期范围内的空气质量数据
2. 支持断点续爬
3. 自动按年份保存数据
4. 错误重试和异常处理
5. 进度跟踪和保存
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import re
import os
import json
from pathlib import Path

class AirQualityScraper:
    """
    空气质量数据爬虫类
    
    负责从网站爬取空气质量数据，支持历史数据获取和断点续爬。
    实现了错误重试、进度保存等功能。
    
    属性:
        base_url (str): 目标网站URL
        headers (dict): 请求头信息
        data_dir (Path): 数据保存目录
        progress_file (Path): 进度文件路径
    """
    
    def __init__(self):
        """
        初始化爬虫
        
        设置基础URL、请求头、数据保存目录等
        """
        self.base_url = "https://www.zq12369.com/environment.php"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.progress_file = self.data_dir / "scraping_progress.json"

    def get_cities_data(self, date, max_retries=3):
        """
        获取指定日期所有城市的空气质量数据
        
        从网站爬取指定日期的全国城市空气质量数据，
        支持失败重试，解析数据并返回DataFrame。
        
        参数:
            date (str): 目标日期，格式'YYYY-MM-DD'
            max_retries (int): 最大重试次数，默认3次
            
        返回:
            DataFrame/None: 包含空气质量数据的DataFrame，失败返回None
        """
        for retry in range(max_retries):
            try:
                # 设置请求参数
                params = {
                    'date': date,
                    'tab': 'rank',
                    'order': 'DESC',
                    'type': 'DAY'
                }
                
                # 发送请求并检查响应
                response = requests.get(self.base_url, params=params, headers=self.headers)
                response.raise_for_status()
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 获取数据表格
                table = soup.find('table', class_='table')
                if not table:
                    print(f"未找到{date}的数据")
                    return None
                    
                data = []
                rows = table.find_all('tr')[1:]  # 跳过表头
                
                # 解析每一行数据
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 7:  # 确保有足够的列
                        # 提取PM2.5数值
                        pm25_text = cols[5].text.strip()
                        pm25_value = re.search(r'(\d+)', pm25_text)
                        pm25 = pm25_value.group(1) if pm25_value else None
                        
                        # 构建城市数据字典
                        city_data = {
                            'rank': cols[0].text.strip(),
                            'province': cols[1].text.strip(),
                            'city': cols[2].text.strip(),
                            'aqi': cols[3].text.strip(),
                            'quality_level': cols[4].text.strip(),
                            'pm25': pm25,
                            'main_pollutant': cols[6].text.strip() if len(cols) > 6 else None,
                            'date': date,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        data.append(city_data)
                
                if data:
                    return pd.DataFrame(data)
                return None
                
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"获取{date}数据时出错，第{retry + 1}/{max_retries}次尝试: {str(e)}")
                    time.sleep(5 * (retry + 1))  # 递增等待时间
                else:
                    print(f"获取{date}数据失败，已尝试{max_retries}次: {str(e)}")
                    return None

    def save_progress(self, last_date):
        """
        保存爬取进度
        
        将最后处理的日期保存到进度文件，用于断点续爬。
        
        参数:
            last_date (str): 最后处理的日期
        """
        progress = {
            'last_date': last_date,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f)

    def load_progress(self):
        """
        加载上次爬取进度
        
        从进度文件中读取上次爬取的最后日期。
        
        返回:
            str/None: 上次爬取的最后日期，如果没有进度文件则返回None
        """
        if self.progress_file.exists():
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
                return progress.get('last_date')
        return None

    def get_historical_data(self, start_date, end_date=None):
        """
        获取指定日期范围内的历史数据
        
        按年份获取并保存指定时间范围内的所有城市空气质量数据。
        支持断点续爬，自动保存进度。
        
        参数:
            start_date (str): 起始日期，格式'YYYY-MM-DD'
            end_date (str): 结束日期，默认为当前日期
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # 检查是否有上次的进度
        last_date = self.load_progress()
        if last_date:
            resume_date = datetime.strptime(last_date, '%Y-%m-%d')
            if resume_date > start:
                print(f"从{last_date}继续爬取")
                start = resume_date + timedelta(days=1)

        current_date = start
        current_year = start.year
        year_data = []
        
        total_days = (end - start).days + 1
        processed_days = 0

        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')
            year = current_date.year
            
            # 如果年份变化，保存前一年的数据
            if year != current_year and year_data:
                self.save_year_data(year_data, current_year)
                year_data = []
                current_year = year
            
            print(f"\r进度: {processed_days}/{total_days} 天 ({processed_days/total_days*100:.2f}%) - 正在获取{date_str}的数据...", end='')
            
            df = self.get_cities_data(date_str)
            if df is not None:
                year_data.append(df)
            
            self.save_progress(date_str)
            
            time.sleep(2)  # 添加延时，避免请求过于频繁
            current_date += timedelta(days=1)
            processed_days += 1

        # 保存最后一年的数据
        if year_data:
            self.save_year_data(year_data, current_year)

        print(f"\n完成！共处理了{processed_days}天的数据。")

    def save_year_data(self, year_data, year):
        """
        保存某一年的数据
        
        将一年的数据合并并保存到CSV文件。
        
        参数:
            year_data (list): 包含该年所有数据的DataFrame列表
            year (int): 年份
        """
        if year_data:
            df = pd.concat(year_data, ignore_index=True)
            filename = self.data_dir / f"air_quality_{year}.csv"
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"\n已将{year}年的数据保存到{filename}")

def main():
    """
    主函数：初始化爬虫并开始爬取数据
    """
    scraper = AirQualityScraper()
    
    # 设置起始日期为2016年1月1日
    start_date = '2016-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"开始获取从{start_date}到{end_date}的历史数据")
    scraper.get_historical_data(start_date, end_date)

if __name__ == "__main__":
    main() 