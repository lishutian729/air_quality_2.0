// 初始化日期选择器
function initializeDatePickers() {
    const today = new Date();
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(today.getDate() - 30);

    document.getElementById('end-date').value = today.toISOString().split('T')[0];
    document.getElementById('start-date').value = thirtyDaysAgo.toISOString().split('T')[0];
}

// 初始化历史数据图表
let historicalChart = null;
function initializeChart() {
    const ctx = document.getElementById('historical-chart').getContext('2d');
    historicalChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'AQI',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1,
                    yAxisID: 'y'
                },
                {
                    label: 'PM2.5',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    tension: 0.1,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'MM-DD HH:mm'
                        }
                    },
                    title: {
                        display: true,
                        text: '时间'
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'AQI'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'PM2.5 (μg/m³)'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            const date = new Date(context[0].parsed.x);
                            return date.toLocaleString('zh-CN');
                        }
                    }
                }
            }
        }
    });
}

// 更新统计信息
function updateStats(data) {
    // AQI统计
    document.getElementById('average-aqi').textContent = data.stats.aqi.mean.toFixed(1);
    document.getElementById('max-aqi').textContent = data.stats.aqi.max.toFixed(1);
    document.getElementById('min-aqi').textContent = data.stats.aqi.min.toFixed(1);

    // PM2.5统计
    document.getElementById('average-pm25').textContent = data.stats.pm25.mean.toFixed(1);
    document.getElementById('max-pm25').textContent = data.stats.pm25.max.toFixed(1);
    document.getElementById('min-pm25').textContent = data.stats.pm25.min.toFixed(1);

    // 数据质量
    document.getElementById('data-points').textContent = data.stats.total_points;
    document.getElementById('missing-ratio').textContent = (data.stats.missing_ratio * 100).toFixed(1) + '%';
    document.getElementById('outlier-ratio').textContent = (data.stats.outlier_ratio * 100).toFixed(1) + '%';
}

// 更新图表数据
function updateChart(data) {
    historicalChart.data.labels = data.timestamps;
    historicalChart.data.datasets[0].data = data.aqi_values;
    historicalChart.data.datasets[1].data = data.pm25_values;
    historicalChart.update();
}

// 更新数据表格
function updateTable(data) {
    const tbody = document.querySelector('#historical-table tbody');
    tbody.innerHTML = '';

    data.timestamps.forEach((timestamp, index) => {
        const row = document.createElement('tr');
        const date = new Date(timestamp);
        const aqiValue = data.aqi_values[index];
        const pm25Value = data.pm25_values[index];
        
        // 获取空气质量等级
        const level = getAQILevel(aqiValue);
        
        row.innerHTML = `
            <td>${date.toLocaleString('zh-CN')}</td>
            <td>${aqiValue.toFixed(1)}</td>
            <td>${pm25Value.toFixed(1)}</td>
            <td><span class="badge" style="background-color: ${level[2]}">${level[1]}</span></td>
        `;
        tbody.appendChild(row);
    });
}

// 获取历史数据
async function fetchHistoricalData() {
    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;

    try {
        const response = await fetch(`/api/historical_data?start_date=${startDate}&end_date=${endDate}`);
        if (!response.ok) {
            throw new Error('获取数据失败');
        }
        const data = await response.json();
        
        updateStats(data);
        updateChart(data);
        updateTable(data);
    } catch (error) {
        console.error('Error:', error);
        showError('获取历史数据失败，请稍后重试');
    }
}

// 显示错误信息
function showError(message) {
    // 创建一个toast提示
    const toastContainer = document.createElement('div');
    toastContainer.style.position = 'fixed';
    toastContainer.style.top = '20px';
    toastContainer.style.right = '20px';
    toastContainer.style.zIndex = '1050';
    
    const toast = document.createElement('div');
    toast.className = 'toast show';
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="toast-header">
            <strong class="me-auto">错误</strong>
            <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    `;
    
    toastContainer.appendChild(toast);
    document.body.appendChild(toastContainer);
    
    // 3秒后自动移除
    setTimeout(() => {
        document.body.removeChild(toastContainer);
    }, 3000);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeDatePickers();
    initializeChart();
    
    // 绑定查询按钮事件
    document.getElementById('filter-btn').addEventListener('click', fetchHistoricalData);
    
    // 首次加载数据
    fetchHistoricalData();
}); 