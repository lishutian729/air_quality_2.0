import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import sys
import os

# 创建数据库连接
engine = create_engine('mysql://root:lst123456@localhost/air_quality')

def import_air_quality_data(csv_path):
    """导入空气质量数据"""
    print("开始导入数据...")
    
    # 读取CSV文件
    print(f"正在读取文件: {csv_path}")
    df = pd.read_csv(csv_path, sep=',', low_memory=False)
    print(f"共读取 {len(df)} 条记录")
    
    # 打印列名
    print("\n数据列名:")
    print(df.columns.tolist())
    
    print("\n数据预览:")
    print(df.head())
    
    # 准备要导入的数据
    data_to_import = pd.DataFrame()
    
    # 转换日期时间格式
    data_to_import['date'] = pd.to_datetime(df['date']).dt.date
    data_to_import['hour'] = df['hour']
    data_to_import['city'] = df['city']
    data_to_import['province'] = df['province']
    data_to_import['aqi'] = df['aqi']
    data_to_import['pm25'] = df['pm25']
    data_to_import['quality_level'] = df['quality_level']
    data_to_import['main_pollutant'] = df['main_pollutant']
    data_to_import['aqi_ma24'] = df['aqi_ma24']
    data_to_import['pm25_ma24'] = df['pm25_ma24']
    data_to_import['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 添加时间戳字段
    current_time = datetime.now()
    data_to_import['created_at'] = current_time
    data_to_import['updated_at'] = current_time
    
    try:
        # 清空现有数据
        with engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE air_quality_data"))
            conn.commit()
            print("\n已清空现有数据")
        
        # 批量插入数据
        batch_size = 1000
        total_batches = len(data_to_import) // batch_size + (1 if len(data_to_import) % batch_size != 0 else 0)
        
        for i in range(0, len(data_to_import), batch_size):
            batch = data_to_import.iloc[i:i+batch_size]
            batch.to_sql('air_quality_data', engine, if_exists='append', index=False)
            current_batch = i // batch_size + 1
            print(f"已导入第 {current_batch}/{total_batches} 批数据")
        
        print("\n数据导入完成！")
        
    except Exception as e:
        print(f"\n导入数据时出错: {str(e)}")
        raise

if __name__ == '__main__':
    csv_path = r"C:\Users\Lbick\Desktop\ai_air_quality\data\processed\hourly_data_processed.csv"
    import_air_quality_data(csv_path) 