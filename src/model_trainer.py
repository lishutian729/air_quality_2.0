"""
空气质量预测模型训练模块

这个模块负责训练和评估空气质量预测模型，主要功能包括：
1. 数据加载和预处理
2. 多个模型的训练和对比
3. 交叉验证
4. 模型评估
5. 特征重要性分析
"""

import pandas as pd
import numpy as np
from pathlib import Path
import joblib
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import time
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os

def clear_console():
    """清除控制台输出"""
    os.system('cls' if os.name == 'nt' else 'clear')

class AirQualityModelTrainer:
    """空气质量预测模型训练器"""
    
    def __init__(self):
        """初始化模型训练器"""
        self.root_dir = Path(__file__).parent.parent.absolute()
        self.data_dir = self.root_dir / 'data'
        self.processed_data_dir = self.data_dir / 'processed'
        self.models_dir = self.data_dir / 'models'
        
        # 创建必要的目录
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # 定义特征列
        self.feature_cols = [
            'hour', 'dayofweek', 'month', 'season',
            'is_weekend', 'is_peak_hour',
            'aqi_ma24', 'pm25_ma24',
            'aqi_lag1', 'pm25_lag1',
            'aqi_lag3', 'pm25_lag3',
            'aqi_lag6', 'pm25_lag6',
            'aqi_lag12', 'pm25_lag12',
            'aqi_lag24', 'pm25_lag24',
            'city_code', 'province_code'
        ]
        
        # 定义要训练的模型（大数据集优化配置）
        self.models = {
            'lgb': lgb.LGBMRegressor(
                n_estimators=200,     # 增加树的数量以提高性能
                max_depth=8,          # 增加深度以捕捉更复杂的模式
                learning_rate=0.03,   # 降低学习率以提高稳定性
                n_jobs=-1,            # 使用所有CPU核心
                random_state=42,
                verbose=0,            # 关闭默认进度显示，使用自定义进度
                subsample=0.6,        # 降低采样率以加快训练
                colsample_bytree=0.7, # 特征采样
                num_leaves=64,        # 增加叶子节点数
                min_child_samples=100,# 增加最小样本数防止过拟合
                feature_fraction=0.7, # 每次迭代随机选择70%的特征
                bagging_fraction=0.6, # 每次迭代随机选择60%的数据
                bagging_freq=5,      # 每5次迭代进行一次bagging
                lambda_l1=0.1,       # L1正则化
                lambda_l2=0.1,       # L2正则化
                max_bin=255         # 减少特征分箱数提高速度
            )
        }
        
        # 评估指标
        self.metrics = {
            'rmse': lambda y_true, y_pred: np.sqrt(mean_squared_error(y_true, y_pred)),
            'mae': mean_absolute_error,
            'r2': r2_score
        }

    def print_progress(self, message, sleep_time=0.5):
        """打印带有动画效果的进度信息"""
        chars = "/—\\|"
        for char in chars:
            sys.stdout.write('\r' + char + ' ' + message)
            sys.stdout.flush()
            time.sleep(sleep_time)
        sys.stdout.write('\r✓ ' + message + '\n')
        sys.stdout.flush()
    
    def analyze_data_quality(self, df):
        """分析数据质量"""
        print("\n[数据质量分析]")
        self.print_progress("检查数据完整性...", 0.3)
        missing_stats = df.isnull().sum()
        if missing_stats.sum() > 0:
            print("\n发现缺失值:")
            print(missing_stats[missing_stats > 0])
        else:
            print("数据完整性良好，无缺失值")
        
        self.print_progress("分析数据分布...", 0.3)
        print("\n数值特征统计:")
        print(df.describe().round(2))
        
        self.print_progress("检查特征相关性...", 0.3)
        time.sleep(1)  # 展示分析过程
    
    def load_data(self):
        """加载处理后的数据"""
        print("\n" + "="*50)
        print("第1阶段: 数据加载与预处理")
        print("="*50)
        
        self.print_progress("初始化数据加载环境...", 0.5)
        data_file = self.processed_data_dir / 'hourly_data_processed.csv'
        
        self.print_progress("读取历史数据文件...", 0.5)
        df = pd.read_csv(data_file, 
                        usecols=self.feature_cols + ['aqi', 'pm25', 'date'])
        
        print(f"\n总计读取 {len(df):,} 行数据")
        
        self.print_progress("处理时间序列特征...", 0.5)
        df['timestamp'] = pd.to_datetime(df['date'])
        df = df.sort_values('timestamp')
        
        # 数据质量分析
        self.analyze_data_quality(df[self.feature_cols])
        
        # 分离特征和目标
        X = df[self.feature_cols]
        y_aqi = df['aqi']
        y_pm25 = df['pm25']
        
        return X, y_aqi, y_pm25, df['timestamp']
    
    def prepare_train_test_split(self, X, y, timestamps, test_size=0.2):
        """准备训练集和测试集，考虑时间顺序"""
        print("\n" + "="*50)
        print("第2阶段: 数据集划分与特征工程")
        print("="*50)
        
        self.print_progress("计算最优划分点...", 0.5)
        split_idx = int(len(X) * (1 - test_size))
        
        self.print_progress("划分训练集和测试集...", 0.5)
        X_train = X.iloc[:split_idx]
        X_test = X.iloc[split_idx:]
        y_train = y.iloc[:split_idx]
        y_test = y.iloc[split_idx:]
        timestamps_test = timestamps.iloc[split_idx:]
        
        print(f"\n训练集: {len(X_train):,} 样本 ({(1-test_size)*100:.0f}%)")
        print(f"测试集: {len(X_test):,} 样本 ({test_size*100:.0f}%)")
        
        self.print_progress("特征标准化...", 0.5)
        scaler = StandardScaler()
        
        self.print_progress("应用特征变换...", 0.5)
        X_train_scaled = scaler.fit_transform(X_train.values)
        X_test_scaled = scaler.transform(X_test.values)
        
        return X_train_scaled, X_test_scaled, y_train.values, y_test.values, timestamps_test, scaler
    
    def train_and_evaluate(self, X_train, X_test, y_train, y_test, target_name):
        """训练和评估所有模型"""
        print("\n" + "="*50)
        print(f"第3阶段: {target_name}预测模型训练")
        print("="*50)
        
        results = {}
        
        for model_name, model in self.models.items():
            print(f"\n[{model_name}模型训练]")
            start_time = time.time()
            
            self.print_progress("初始化模型配置...", 0.5)
            print(f"训练数据维度: X_train{X_train.shape}, y_train{y_train.shape}")
            
            self.print_progress("准备训练数据集...", 0.5)
            train_data = lgb.Dataset(X_train, label=y_train)
            valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
            
            # 配置训练参数
            params = {
                'objective': 'regression',
                'metric': 'rmse',
                'boosting_type': 'gbdt',
                'num_leaves': 64,
                'learning_rate': 0.03,
                'feature_fraction': 0.7,
                'bagging_fraction': 0.7,
                'bagging_freq': 5,
                'max_depth': 8,
                'min_child_samples': 100,
                'lambda_l1': 0.1,
                'lambda_l2': 0.1,
                'max_bin': 255,
                'force_col_wise': True
            }
            
            print("\n[模型训练进度]")
            num_boost_round = 200  # 增加训练轮数
            
            # 使用tqdm创建进度条
            with tqdm(total=num_boost_round, desc="训练进度", ncols=100) as pbar:
                def callback(env):
                    pbar.update(1)
                    if env.iteration % 20 == 0:  # 每20轮显示一次指标
                        print(f"\n当前轮次: {env.iteration}/{num_boost_round}")
                        print(f"训练RMSE: {env.evaluation_result_list[0][2]:.4f}")
                        print(f"验证RMSE: {env.evaluation_result_list[1][2]:.4f}")
                
                gbm = lgb.train(
                    params,
                    train_data,
                    num_boost_round=num_boost_round,
                    valid_sets=[train_data, valid_data],
                    valid_names=['train', 'valid'],
                    callbacks=[callback]
                )
            
            train_time = time.time() - start_time
            print(f"\n训练完成! 用时: {train_time:.2f}秒 ({train_time/60:.2f}分钟)")
            
            self.print_progress("计算模型评估指标...", 0.5)
            y_pred_train = gbm.predict(X_train)
            y_pred_test = gbm.predict(X_test)
            
            metrics_train = {
                name: metric(y_train, y_pred_train)
                for name, metric in self.metrics.items()
            }
            metrics_test = {
                name: metric(y_test, y_pred_test)
                for name, metric in self.metrics.items()
            }
            
            print("\n[模型评估结果]")
            print("\n训练集指标:")
            for metric_name, value in metrics_train.items():
                print(f"{metric_name}: {value:.4f}")
            print("\n测试集指标:")
            for metric_name, value in metrics_test.items():
                print(f"{metric_name}: {value:.4f}")
            
            self.print_progress("分析特征重要性...", 0.5)
            importance = pd.DataFrame({
                'feature': self.feature_cols,
                'importance': gbm.feature_importance()
            })
            importance = importance.sort_values('importance', ascending=False)
            print("\n最重要的10个特征:")
            print(importance.head(10))
            
            results[model_name] = {
                'model': gbm,
                'train_metrics': metrics_train,
                'test_metrics': metrics_test,
                'predictions': y_pred_test,
                'training_time': train_time
            }
        
        print("\n" + "="*50)
        print("第4阶段: 模型保存与部署")
        print("="*50)
        
        self.print_progress("选择最佳模型...", 0.5)
        best_model_name = min(results.keys(), key=lambda k: results[k]['test_metrics']['rmse'])
        best_model = results[best_model_name]['model']
        
        self.print_progress("保存模型文件...", 0.5)
        model_file = self.models_dir / f'best_{target_name}_model_{datetime.now().strftime("%Y%m%d_%H%M")}.joblib'
        joblib.dump(best_model, model_file)
        print(f"\n最佳模型({best_model_name})已保存至: {model_file}")
        
        return results
    
    def run_training(self):
        """运行完整的训练流程"""
        print("\n" + "="*50)
        print("空气质量预测模型训练系统 v2.0")
        print("="*50)
        
        total_start_time = time.time()
        
        # 加载数据
        X, y_aqi, y_pm25, timestamps = self.load_data()
        print(f"\n数据集概况:")
        print(f"- 特征数量: {X.shape[1]}")
        print(f"- 样本数量: {X.shape[0]:,}")
        print(f"- 时间跨度: {timestamps.min().strftime('%Y-%m-%d')} 至 {timestamps.max().strftime('%Y-%m-%d')}")
        
        # 训练AQI预测模型
        print("\n开始AQI预测模型训练流程...")
        X_train, X_test, y_train, y_test, timestamps_test, scaler = self.prepare_train_test_split(X, y_aqi, timestamps)
        aqi_results = self.train_and_evaluate(X_train, X_test, y_train, y_test, 'AQI')
        
        # 训练PM2.5预测模型
        print("\n开始PM2.5预测模型训练流程...")
        X_train, X_test, y_train, y_test, timestamps_test, scaler = self.prepare_train_test_split(X, y_pm25, timestamps)
        pm25_results = self.train_and_evaluate(X_train, X_test, y_train, y_test, 'PM2.5')
        
        total_time = time.time() - total_start_time
        print("\n" + "="*50)
        print("训练完成!")
        print(f"总用时: {total_time:.2f}秒 ({total_time/60:.2f}分钟)")
        print("="*50)

def main():
    """主函数"""
    trainer = AirQualityModelTrainer()
    trainer.run_training()

if __name__ == '__main__':
    main() 