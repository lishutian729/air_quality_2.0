"""
空气质量数据处理模块

这个模块负责处理原始的空气质量数据，将日级别的数据转换为小时级别的数据，
并添加各种特征用于后续的机器学习模型训练。主要功能包括：
1. 读取原始数据文件（支持多种中文编码）
2. 生成小时级别的变化系数
3. 基于日数据生成小时级别的数据
4. 添加时间相关特征
5. 计算统计特征（如移动平均）
6. 数据标准化
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import joblib
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import interp1d

class AirQualityDataProcessor:
    """
    空气质量数据处理器类
    
    负责将原始的日级别空气质量数据处理成小时级别的数据，并添加必要的特征。
    
    属性:
        data_dir (Path): 数据目录的路径
        processed_data_dir (Path): 处理后数据存储的目录路径
        scalers (dict): 存储数据标准化器的字典
    """
    
    def __init__(self):
        """初始化数据处理器"""
        # 设置数据目录
        self.root_dir = Path(__file__).parent.parent.absolute()
        self.src_data_dir = self.root_dir / 'src' / 'data'
        self.data_dir = self.root_dir / 'data'
        self.processed_data_dir = self.data_dir / 'processed'
        self.plots_dir = self.data_dir / 'plots'
        
        # 创建必要的目录
        for dir_path in [self.processed_data_dir, self.plots_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # 用于存储数据统计信息
        self.scalers = {}
        
        # 定义数据范围限制
        self.aqi_range = (0, 500)      # AQI的标准范围是0-500
        self.pm25_range = (0, 500)     # PM2.5的范围限制在0-500

        # 定义不同情况下的小时变化模式
        self.patterns = {
            'workday': {  # 工作日模式
                'morning_peak': {'hours': [7,8,9], 'factor': 1.15},  # 降低峰值
                'afternoon_low': {'hours': [12,13,14], 'factor': 0.85},
                'evening_peak': {'hours': [17,18,19], 'factor': 1.20},
                'night_low': {'hours': [2,3,4], 'factor': 0.80}
            },
            'weekend': {  # 周末模式
                'morning_peak': {'hours': [9,10,11], 'factor': 1.05},
                'afternoon_peak': {'hours': [14,15,16], 'factor': 1.10},
                'evening_peak': {'hours': [19,20,21], 'factor': 1.12},
                'night_low': {'hours': [2,3,4], 'factor': 0.85}
            }
        }
        
        # 修改季节影响因子
        self.season_factors = {
            1: 1.15,  # 冬季：供暖期污染加重，但降低系数
            2: 1.05,  # 春季：扬尘等影响
            3: 0.90,  # 夏季：降水导致污染物沉降
            4: 1.0    # 秋季：基准水平
        }

        # 添加天气持续性影响
        self.weather_persistence = 0.7  # 天气持续性因子

    def validate_data(self, df, stage='unknown'):
        """验证数据的有效性"""
        print(f"\n开始数据验证... (阶段: {stage})")
        
        # 检查并处理异常值
        print("\n检查异常值...")
        for col in ['pm25', 'aqi']:
            if col in df.columns:
                invalid_count = df[df[col].isin([float('-inf'), float('inf')]) | df[col].isna()].shape[0]
                print(f"{col}无效值数量: {invalid_count}")
                print(f"{col}统计信息:")
                print(df[col].describe())
                
                # 绘制分布图
                plt.figure(figsize=(10, 6))
                sns.histplot(data=df, x=col, bins=50)
                plt.title(f'{col}分布图 ({stage})')
                plt.savefig(self.plots_dir / f'{col}_dist_{stage}.png')
                plt.close()
        
        # 检查时间特征的分布
        if 'hour' in df.columns:
            print("\n时间特征分布:")
            for col in ['hour', 'day', 'month', 'dayofweek', 'season']:
                if col in df.columns:
                    print(f"\n{col}值分布:")
                    print(df[col].value_counts().sort_index())
        
        # 检查分类特征的分布
        if 'quality_level' in df.columns:
            print("\n空气质量等级分布:")
            print(df['quality_level'].value_counts())
        
        # 移除或修正异常值
        for col in ['pm25', 'aqi']:
            if col in df.columns:
                original_values = df[col].copy()
                df[col] = df[col].clip(
                    self.pm25_range[0] if 'pm25' in col else self.aqi_range[0],
                    self.pm25_range[1] if 'pm25' in col else self.aqi_range[1]
                )
                clipped_count = (original_values != df[col]).sum()
                if clipped_count > 0:
                    print(f"\n{col}中有{clipped_count}个值被截断到有效范围内")
        
        return df

    def get_hour_factor(self, hour, is_weekend, season):
        """获取小时变化因子"""
        pattern = self.patterns['weekend'] if is_weekend else self.patterns['workday']
        base_factor = 1.0
        
        # 应用时段因子
        for period in pattern.values():
            if hour in period['hours']:
                base_factor = period['factor']
                break
        
        # 应用季节因子
        season_factor = self.season_factors[season]
        
        return base_factor * season_factor

    def generate_smooth_daily_curve(self, base_value, date, is_weekend, season, prev_day_values=None):
        """生成平滑的日变化曲线，考虑天气持续性"""
        # 生成24小时的基础变化因子
        hour_factors = [self.get_hour_factor(h, is_weekend, season) for h in range(24)]
        
        # 使用三次样条插值生成平滑曲线
        x = np.arange(24)
        y = np.array(hour_factors) * base_value
        
        # 为了确保曲线首尾相连，我们在首尾添加额外的点
        x_extended = np.concatenate([x-24, x, x+24])
        y_extended = np.concatenate([y, y, y])
        
        # 创建三次样条插值
        f = interp1d(x_extended, y_extended, kind='cubic')
        
        # 生成平滑的24小时曲线
        smooth_values = f(x)
        
        # 考虑前一天的影响
        if prev_day_values is not None:
            # 确保平滑过渡
            smooth_values[0] = prev_day_values[-1] * 0.7 + smooth_values[0] * 0.3
            for i in range(1, 4):  # 前3个小时平滑过渡
                smooth_values[i] = smooth_values[i-1] * 0.6 + smooth_values[i] * 0.4
        
        # 添加小幅随机波动（±3%）
        random_factors = np.random.normal(1, 0.03, 24)
        smooth_values = smooth_values * random_factors
        
        # 应用天气持续性
        if prev_day_values is not None:
            smooth_values = prev_day_values * self.weather_persistence + smooth_values * (1 - self.weather_persistence)
        
        return np.clip(smooth_values, 0, self.aqi_range[1])

    def process_data(self, input_file):
        """处理数据的主函数"""
        print(f"开始处理数据文件: {input_file}")
        
        try:
            # 读取CSV文件
            df = pd.read_csv(input_file)
            print("\n原始数据信息:")
            print(df.info())
            
            # 初始数据验证
            df = self.validate_data(df, '原始数据')
            
            # 生成小时数据
            hourly_data = []
            
            # 按城市分组处理数据
            for city in df['city'].unique():
                city_data = df[df['city'] == city].copy()
                city_data = city_data.sort_values('date')
                
                prev_day_aqi = None
                prev_day_pm25 = None
                
                # 确保日期连续
                date_range = pd.date_range(
                    start=pd.to_datetime(city_data['date'].min()),
                    end=pd.to_datetime(city_data['date'].max())
                )
                
                for date in date_range:
                    # 获取当天的数据，如果没有则使用前一天的数据
                    date_str = date.strftime('%Y-%m-%d')
                    date_data = city_data[city_data['date'] == date_str]
                    
                    if len(date_data) == 0:
                        # 如果当天没有数据，使用前一天的数据
                        prev_date = (date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                        date_data = city_data[city_data['date'] == prev_date]
                        if len(date_data) == 0:
                            continue
                    
                    # 获取基准值
                    base_aqi = float(date_data['aqi'].iloc[0])
                    base_pm25 = float(date_data['pm25'].iloc[0])
                    
                    # 获取日期特征
                    is_weekend = date.weekday() >= 5
                    season = (date.month % 12 + 3) // 3
                    
                    # 生成平滑的日变化曲线
                    daily_aqi = self.generate_smooth_daily_curve(
                        base_aqi, date, is_weekend, season, prev_day_aqi
                    )
                    daily_pm25 = self.generate_smooth_daily_curve(
                        base_pm25, date, is_weekend, season, prev_day_pm25
                    )
                    
                    # 更新前一天的值
                    prev_day_aqi = daily_aqi
                    prev_day_pm25 = daily_pm25
                    
                    # 生成24小时的数据
                    for hour in range(24):
                        # 获取该小时的AQI和PM2.5值
                        hourly_aqi = daily_aqi[hour]
                        hourly_pm25 = daily_pm25[hour]
                        
                        # 确定空气质量等级
                        if hourly_aqi <= 50:
                            quality_level = '优'
                        elif hourly_aqi <= 100:
                            quality_level = '良'
                        elif hourly_aqi <= 150:
                            quality_level = '轻度污染'
                        elif hourly_aqi <= 200:
                            quality_level = '中度污染'
                        elif hourly_aqi <= 300:
                            quality_level = '重度污染'
                        else:
                            quality_level = '严重污染'
                        
                        hourly_data.append({
                            'date': date_str,
                            'hour': hour,
                            'city': city,
                            'province': date_data['province'].iloc[0],
                            'aqi': hourly_aqi,
                            'pm25': hourly_pm25,
                            'quality_level': quality_level,
                            'main_pollutant': date_data['main_pollutant'].iloc[0]
                        })
            
            hourly_df = pd.DataFrame(hourly_data)
            
            # 验证小时数据
            hourly_df = self.validate_data(hourly_df, '小时化后')
            
            # 添加时间特征
            hourly_df['timestamp'] = hourly_df.apply(
                lambda x: pd.Timestamp(x['date']).replace(hour=x['hour']),
                axis=1
            )
            hourly_df['year'] = hourly_df['timestamp'].dt.year
            hourly_df['month'] = hourly_df['timestamp'].dt.month
            hourly_df['day'] = hourly_df['timestamp'].dt.day
            hourly_df['dayofweek'] = hourly_df['timestamp'].dt.dayofweek
            hourly_df['season'] = (hourly_df['month'] % 12 + 3) // 3
            hourly_df['is_weekend'] = hourly_df['dayofweek'].isin([5, 6]).astype(int)
            hourly_df['is_peak_hour'] = hourly_df.apply(
                lambda x: int(hour in self.patterns['weekend' if x['is_weekend'] else 'workday']['morning_peak']['hours'] or 
                            hour in self.patterns['weekend' if x['is_weekend'] else 'workday']['evening_peak']['hours']),
                axis=1
            )
            
            # 计算24小时移动平均
            print("\n计算移动平均...")
            for col in ['aqi', 'pm25']:
                ma_col = f'{col}_ma24'
                hourly_df[ma_col] = hourly_df.groupby('city')[col].transform(
                    lambda x: x.rolling(window=24, min_periods=1, center=False).mean()
                )
                if col == 'aqi':
                    hourly_df[ma_col] = hourly_df[ma_col].clip(self.aqi_range[0], self.aqi_range[1])
                else:
                    hourly_df[ma_col] = hourly_df[ma_col].clip(self.pm25_range[0], self.pm25_range[1])
            
            # 添加滞后特征
            print("计算滞后特征...")
            for i in [1, 3, 6, 12, 24]:
                for col in ['aqi', 'pm25']:
                    lag_col = f'{col}_lag{i}'
                    hourly_df[lag_col] = hourly_df.groupby('city')[col].shift(i)
                    hourly_df[lag_col] = hourly_df[lag_col].fillna(method='ffill').fillna(method='bfill')
                    if col == 'aqi':
                        hourly_df[lag_col] = hourly_df[lag_col].clip(self.aqi_range[0], self.aqi_range[1])
                    else:
                        hourly_df[lag_col] = hourly_df[lag_col].clip(self.pm25_range[0], self.pm25_range[1])
            
            # 类别特征编码
            hourly_df['city_code'] = pd.Categorical(hourly_df['city']).codes
            hourly_df['province_code'] = pd.Categorical(hourly_df['province']).codes
            hourly_df['quality_level_code'] = pd.Categorical(hourly_df['quality_level']).codes
            
            # 验证特征工程后的数据
            hourly_df = self.validate_data(hourly_df, '特征工程后')
            
            # 保存数据
            original_file = self.processed_data_dir / 'hourly_data_original.csv'
            processed_file = self.processed_data_dir / 'hourly_data_processed.csv'
            
            hourly_df.to_csv(original_file, index=False, encoding='utf-8-sig')
            hourly_df.to_csv(processed_file, index=False, encoding='utf-8-sig')
            
            # 保存数据范围信息
            scalers = {
                'aqi_range': self.aqi_range,
                'pm25_range': self.pm25_range
            }
            joblib.dump(scalers, self.processed_data_dir / 'scalers.joblib')
            
            # 生成数据分析图表
            self._generate_analysis_plots(hourly_df)
            
            print("\n数据处理完成！")
            
        except Exception as e:
            print(f"数据处理过程中出错: {str(e)}")
            raise
    
    def _generate_analysis_plots(self, df):
        """生成数据分析图表"""
        # 创建24小时变化曲线图
        plt.figure(figsize=(15, 6))
        for day_type in ['工作日', '周末']:
            mask = df['is_weekend'] == (1 if day_type == '周末' else 0)
            hourly_means = df[mask].groupby('hour')['aqi'].mean()
            plt.plot(hourly_means.index, hourly_means.values, 
                    label=day_type, marker='o')
        
        plt.title('24小时AQI变化曲线')
        plt.xlabel('小时')
        plt.ylabel('AQI')
        plt.legend()
        plt.grid(True)
        plt.savefig(self.plots_dir / 'daily_pattern.png')
        plt.close()
        
        # 创建季节变化箱线图
        plt.figure(figsize=(12, 6))
        sns.boxplot(data=df, x='season', y='aqi')
        plt.title('季节AQI分布')
        plt.xlabel('季节')
        plt.ylabel('AQI')
        plt.savefig(self.plots_dir / 'seasonal_pattern.png')
        plt.close()
        
        # 创建相关性热图
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        corr_matrix = df[numeric_cols].corr()
        plt.figure(figsize=(15, 12))
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0)
        plt.title('特征相关性矩阵')
        plt.tight_layout()
        plt.savefig(self.plots_dir / 'feature_correlations.png')
        plt.close()

def main():
    """
    主函数：初始化数据处理器并处理数据
    """
    processor = AirQualityDataProcessor()
    
    # 查找数据文件
    input_files = list(processor.src_data_dir.glob('air_quality_*.csv'))
    if not input_files:
        raise FileNotFoundError(f"在{processor.src_data_dir}目录下未找到air_quality_*.csv文件")
    
    print(f"找到以下数据文件:")
    for file in input_files:
        print(f"- {file}")
    
    # 处理第一个找到的文件
    input_file = input_files[0]
    print(f"\n将处理文件: {input_file}")
    
    processor.process_data(input_file)

if __name__ == '__main__':
    main() 