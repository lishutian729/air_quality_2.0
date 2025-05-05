// AQI等级配置
const AQI_CONFIG = {
    excellent: {
        max: 50,
        color: '#00e400',
        text: '优'
    },
    good: {
        max: 100,
        color: '#ffff00',
        text: '良'
    },
    moderate: {
        max: 150,
        color: '#ff7e00',
        text: '轻度污染'
    },
    unhealthy: {
        max: 200,
        color: '#ff0000',
        text: '中度污染'
    },
    veryUnhealthy: {
        max: 300,
        color: '#99004c',
        text: '重度污染'
    },
    hazardous: {
        max: 500,
        color: '#7e0023',
        text: '严重污染'
    }
};

// 获取AQI等级
function getAQILevel(aqi) {
    if (aqi <= AQI_CONFIG.excellent.max) return ['excellent', AQI_CONFIG.excellent.text, AQI_CONFIG.excellent.color];
    if (aqi <= AQI_CONFIG.good.max) return ['good', AQI_CONFIG.good.text, AQI_CONFIG.good.color];
    if (aqi <= AQI_CONFIG.moderate.max) return ['moderate', AQI_CONFIG.moderate.text, AQI_CONFIG.moderate.color];
    if (aqi <= AQI_CONFIG.unhealthy.max) return ['unhealthy', AQI_CONFIG.unhealthy.text, AQI_CONFIG.unhealthy.color];
    if (aqi <= AQI_CONFIG.veryUnhealthy.max) return ['very-unhealthy', AQI_CONFIG.veryUnhealthy.text, AQI_CONFIG.veryUnhealthy.color];
    return ['hazardous', AQI_CONFIG.hazardous.text, AQI_CONFIG.hazardous.color];
}

// 更新AQI显示
function updateAQIDisplay(value, elementId, levelElementId) {
    const element = document.getElementById(elementId);
    const levelElement = document.getElementById(levelElementId);
    
    if (element && value != null) {
        const [level, text, color] = getAQILevel(value);
        element.textContent = Math.round(value);
        element.style.color = color;
        
        if (levelElement) {
            levelElement.textContent = text;
            levelElement.style.color = color;
        }
    }
}

// 初始化图表
let predictionChart = null;
function initChart() {
    const ctx = document.getElementById('prediction-chart').getContext('2d');
    predictionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: '实际AQI',
                data: [],
                borderColor: '#2196F3',
                fill: false
            }, {
                label: '预测AQI',
                data: [],
                borderColor: '#4CAF50',
                fill: false
            }, {
                label: '置信区间',
                data: [],
                backgroundColor: 'rgba(76, 175, 80, 0.1)',
                borderColor: 'transparent',
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label: function(context) {
                            const value = context.raw;
                            if (value === null) return null;
                            const [_, text] = getAQILevel(value);
                            return `${context.dataset.label}: ${Math.round(value)} (${text})`;
                        }
                    }
                },
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 500,
                    title: {
                        display: true,
                        text: 'AQI'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '时间'
                    }
                }
            }
        }
    });
}

// 更新图表数据
async function updateChart(timeRange) {
    try {
        // 显示加载动画
        document.querySelector('.chart-container').classList.add('loading');
        
        const response = await fetch(`/api/predictions?range=${timeRange}`);
        if (!response.ok) {
            throw new Error('获取数据失败');
        }
        
        const data = await response.json();
        
        // 更新图表数据
        predictionChart.data.labels = data.timestamps;
        predictionChart.data.datasets[0].data = data.actual;
        predictionChart.data.datasets[1].data = data.predicted;
        predictionChart.data.datasets[2].data = data.confidence;
        predictionChart.update();

        // 更新当前AQI和预测值
        if (data.actual.length > 0) {
            const currentAQI = data.actual[data.actual.length - 1];
            updateAQIDisplay(currentAQI, 'current-aqi', 'current-level');
        }
        
        if (data.predicted.length > 0) {
            const predictedAQI = data.predicted[0];
            updateAQIDisplay(predictedAQI, 'prediction-24h', 'prediction-level');
        }

        // 更新置信区间
        if (data.confidence && data.confidence.length > 0) {
            const [lower, upper] = data.confidence[0];
            const confidenceElement = document.getElementById('confidence-interval');
            if (confidenceElement) {
                confidenceElement.textContent = `${Math.round(lower)}-${Math.round(upper)}`;
            }
        }

        // 更新预测表格
        updatePredictionTable(data);
        
    } catch (error) {
        console.error('Error fetching prediction data:', error);
        showError('获取数据失败，请稍后重试');
    } finally {
        // 移除加载动画
        document.querySelector('.chart-container').classList.remove('loading');
    }
}

// 更新预测表格
function updatePredictionTable(data) {
    const table = document.getElementById('prediction-table');
    if (!table) return;

    table.innerHTML = '';
    
    for (let i = 0; i < data.timestamps.length; i++) {
        const row = document.createElement('tr');
        const predictedValue = data.predicted[i];
        const actualValue = data.actual[i];
        const [_, text, color] = getAQILevel(predictedValue);
        
        row.innerHTML = `
            <td>${data.timestamps[i]}</td>
            <td style="color: ${color}">${Math.round(predictedValue)}</td>
            <td>${actualValue ? Math.round(actualValue) : '-'}</td>
            <td>${actualValue ? Math.round(Math.abs(actualValue - predictedValue)) : '-'}</td>
            <td style="color: ${color}">${text}</td>
        `;
        table.appendChild(row);
    }
}

// 显示错误消息
function showError(message) {
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    document.querySelector('.container').insertAdjacentHTML('afterbegin', alertHtml);
}

// 初始化页面
document.addEventListener('DOMContentLoaded', function() {
    // 初始化图表
    initChart();
    
    // 初始化时间范围选择器
    document.querySelectorAll('.time-selector button').forEach(button => {
        button.addEventListener('click', (e) => {
            document.querySelector('.time-selector button.active').classList.remove('active');
            e.target.classList.add('active');
            updateChart(e.target.dataset.range);
        });
    });
    
    // 初始加载
    updateChart('24h');
    
    // 定期更新数据
    setInterval(() => {
        const activeRange = document.querySelector('.time-selector button.active').dataset.range;
        updateChart(activeRange);
    }, 300000); // 每5分钟更新一次
}); 