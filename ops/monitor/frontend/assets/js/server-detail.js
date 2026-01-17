/**
 * 服务器详情页逻辑
 * 
 * 负责展示单个服务器的详细指标和历史趋势
 */

let serverId = null;
let server = null;
let chart = null;
let currentRange = 24; // 默认 24 小时
let currentMetric = 'cpu_pct';
let refreshTimer = null;

/**
 * 初始化页面
 */
async function init() {
    // 获取 URL 参数中的服务器 ID
    const params = new URLSearchParams(window.location.search);
    serverId = params.get('id');

    if (!serverId) {
        showToast('缺少服务器 ID 参数', 'danger');
        return;
    }

    // 初始化图表
    initChart();

    // 绑定事件
    bindEvents();

    // 加载数据
    await loadServerDetail();
    await loadTimeseries();

    // 启动自动刷新
    startAutoRefresh();
}

/**
 * 初始化 ECharts 图表
 */
function initChart() {
    const chartDom = document.getElementById('timeseries-chart');
    chart = echarts.init(chartDom);

    // 响应式调整
    window.addEventListener('resize', () => {
        chart.resize();
    });
}

/**
 * 绑定事件监听器
 */
function bindEvents() {
    // 时间范围选择
    document.querySelectorAll('.time-range-selector button').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            // 更新按钮状态
            document.querySelectorAll('.time-range-selector button').forEach(b => {
                b.classList.remove('btn-primary');
            });
            e.target.classList.add('btn-primary');

            // 更新范围并重新加载
            currentRange = parseInt(e.target.dataset.range);
            await loadTimeseries();
        });
    });

    // 指标选择
    document.getElementById('metric-selector').addEventListener('change', async (e) => {
        currentMetric = e.target.value;
        await loadTimeseries();
    });
}

/**
 * 加载服务器详情
 */
async function loadServerDetail() {
    try {
        // 先获取所有服务器，找到当前服务器
        const servers = await api.getServers();
        server = servers.find(s => s.id == serverId);

        if (!server) {
            showToast('服务器不存在', 'danger');
            return;
        }

        renderServerDetail(server);
    } catch (error) {
        console.error('Failed to load server detail:', error);
        showToast(`加载失败: ${error.message}`, 'danger');
    }
}

/**
 * 渲染服务器详情
 */
function renderServerDetail(server) {
    const online = server.online;
    const latest = server.latest || {};

    // 页面标题
    document.getElementById('server-name').textContent = server.name;
    document.title = `${server.name} - 服务器详情`;

    // 状态徽章
    const statusBadge = document.getElementById('status-badge');
    if (online) {
        statusBadge.className = 'badge badge-lg bg-green';
        statusBadge.innerHTML = '<span class="status-indicator online"></span> 在线';
    } else {
        statusBadge.className = 'badge badge-lg bg-red';
        statusBadge.innerHTML = '<span class="status-indicator offline"></span> 离线';
    }

    // CPU
    const cpuValue = latest.cpu_pct;
    document.getElementById('current-cpu').textContent = formatPercent(cpuValue);
    const cpuProgress = document.getElementById('cpu-progress');
    cpuProgress.style.width = `${cpuValue || 0}%`;
    cpuProgress.className = `progress-bar ${getProgressColorClass(cpuValue)}`;

    // 磁盘
    const diskValue = latest.disk_used_pct;
    document.getElementById('current-disk').textContent = formatPercent(diskValue);
    if (latest.disk_used_bytes && latest.disk_total_bytes) {
        document.getElementById('disk-detail').textContent =
            `${formatBytes(latest.disk_used_bytes)} / ${formatBytes(latest.disk_total_bytes)}`;
    }

    // GPU
    const gpuValue = latest.gpu_util_pct;
    if (gpuValue !== null && gpuValue !== undefined) {
        document.getElementById('current-gpu').textContent = formatPercent(gpuValue);
        if (latest.gpu_mem_used_mb && latest.gpu_mem_total_mb) {
            document.getElementById('gpu-detail').textContent =
                `显存: ${latest.gpu_mem_used_mb} / ${latest.gpu_mem_total_mb} MB`;
        }
    } else {
        document.getElementById('current-gpu').textContent = 'N/A';
        document.getElementById('gpu-detail').textContent = '无 GPU 或不可用';
    }

    // 最后更新
    document.getElementById('last-update').textContent = formatRelativeTime(latest.ts);
    document.getElementById('server-info').textContent = `${server.host}:${server.agent_port}`;

    // 服务状态
    renderServices(server);
}

/**
 * 渲染服务状态列表
 */
function renderServices(server) {
    const container = document.getElementById('services-list');
    const services = server.services_config ? JSON.parse(server.services_config || '[]') : [];

    if (!services || services.length === 0) {
        container.innerHTML = `
      <div class="text-center text-muted py-4">
        <i class="ti ti-info-circle me-2"></i>
        未配置服务监控
      </div>
    `;
        return;
    }

    // 注意：这里的 services 是配置的服务列表，不是实时状态
    // 实际状态需要从 API 获取，但目前接口可能未提供
    container.innerHTML = `
    <div class="row g-3">
      ${services.map(svc => `
        <div class="col-md-4 col-lg-3">
          <div class="card card-sm">
            <div class="card-body d-flex align-items-center">
              <span class="service-badge active">
                <i class="ti ti-circle-check me-1"></i>
                ${escapeHtml(svc)}
              </span>
            </div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

/**
 * 加载时间序列数据
 */
async function loadTimeseries() {
    try {
        const to = new Date().toISOString();
        const from = new Date(Date.now() - currentRange * 3600000).toISOString();

        const data = await api.getTimeseries(serverId, currentMetric, from, to, 'avg');
        renderChart(data);
    } catch (error) {
        console.error('Failed to load timeseries:', error);
        // 显示空图表
        renderEmptyChart();
    }
}

/**
 * 渲染图表
 */
function renderChart(data) {
    if (!data || !data.data || data.data.length === 0) {
        renderEmptyChart();
        return;
    }

    const metricLabels = {
        'cpu_pct': 'CPU 使用率 (%)',
        'disk_used_pct': '磁盘使用率 (%)',
        'gpu_util_pct': 'GPU 使用率 (%)'
    };

    const metricColors = {
        'cpu_pct': '#4299e1',
        'disk_used_pct': '#f59f00',
        'gpu_util_pct': '#2fb344'
    };

    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: function (params) {
                const time = new Date(params[0].value[0]).toLocaleString('zh-CN');
                const value = params[0].value[1]?.toFixed(1) || '-';
                return `${time}<br/>${metricLabels[currentMetric]}: ${value}%`;
            }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            top: '10%',
            containLabel: true
        },
        xAxis: {
            type: 'time',
            axisLine: { lineStyle: { color: '#e9ecef' } },
            axisLabel: {
                color: '#868e96',
                formatter: function (value) {
                    const date = new Date(value);
                    if (currentRange <= 24) {
                        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    }
                    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
                }
            }
        },
        yAxis: {
            type: 'value',
            min: 0,
            max: 100,
            axisLine: { show: false },
            axisLabel: { color: '#868e96' },
            splitLine: { lineStyle: { color: '#e9ecef' } }
        },
        series: [{
            name: metricLabels[currentMetric],
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            showSymbol: false,
            lineStyle: {
                color: metricColors[currentMetric],
                width: 2
            },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: metricColors[currentMetric] + '40' },
                    { offset: 1, color: metricColors[currentMetric] + '05' }
                ])
            },
            itemStyle: {
                color: metricColors[currentMetric]
            },
            data: data.data.map(d => [d.ts, d.value])
        }]
    };

    chart.setOption(option);
}

/**
 * 渲染空图表
 */
function renderEmptyChart() {
    const option = {
        title: {
            text: '暂无数据',
            left: 'center',
            top: 'center',
            textStyle: {
                color: '#868e96',
                fontSize: 16,
                fontWeight: 'normal'
            }
        },
        xAxis: { show: false },
        yAxis: { show: false }
    };

    chart.setOption(option, true);
}

/**
 * 启动自动刷新
 */
function startAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(async () => {
        await loadServerDetail();
        // 图表不需要太频繁刷新
    }, REFRESH_INTERVAL);
}

/**
 * 停止自动刷新
 */
function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 页面隐藏时停止刷新，显示时恢复
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        loadServerDetail();
        startAutoRefresh();
    }
});
