/**
 * 概览页逻辑
 * 
 * 负责展示服务器卡片网格和统计信息
 */

let servers = [];
let refreshTimer = null;

/**
 * 初始化页面
 */
async function init() {
    await loadServers();
    startAutoRefresh();
}

/**
 * 加载服务器列表
 */
async function loadServers() {
    try {
        servers = await api.getServers();
        renderServerCards(servers);
        updateStats(servers);
        updateLastUpdateTime();
    } catch (error) {
        console.error('Failed to load servers:', error);
        showToast(`加载失败: ${error.message}`, 'danger');
        renderError();
    }
}

/**
 * 渲染服务器卡片
 */
function renderServerCards(servers) {
    const container = document.getElementById('server-cards');

    if (!servers || servers.length === 0) {
        container.innerHTML = `
      <div class="col-12">
        <div class="empty-state">
          <i class="ti ti-server-off" style="font-size: 64px; opacity: 0.5;"></i>
          <h3>暂无服务器</h3>
          <p>还没有添加任何服务器</p>
          <a href="servers-manage.html" class="btn btn-primary">
            <i class="ti ti-plus me-1"></i>添加服务器
          </a>
        </div>
      </div>
    `;
        return;
    }

    container.innerHTML = servers.map(server => renderServerCard(server)).join('');
}

/**
 * 渲染单个服务器卡片
 */
function renderServerCard(server) {
    const online = server.online;
    const latest = server.latest || {};

    const cpuValue = latest.cpu_pct;
    const diskValue = latest.disk_used_pct;
    const gpuValue = latest.gpu_util_pct;
    const failedServices = latest.services_failed_count || 0;

    return `
    <div class="col-sm-6 col-lg-4">
      <div class="card server-card">
        <div class="card-header">
          <div class="d-flex align-items-center w-100">
            <span class="status-indicator ${online ? 'online' : 'offline'}"></span>
            <h3 class="card-title mb-0 flex-grow-1">${escapeHtml(server.name)}</h3>
            ${failedServices > 0 ? `
              <span class="badge bg-danger">${failedServices} 服务异常</span>
            ` : ''}
          </div>
        </div>
        <div class="card-body">
          <!-- 服务器信息 -->
          <div class="mb-3 text-muted small">
            <i class="ti ti-network me-1"></i>${escapeHtml(server.host)}:${server.agent_port}
          </div>
          
          ${online ? `
            <!-- CPU 使用率 -->
            <div class="mb-3">
              <div class="d-flex justify-content-between mb-1">
                <span class="metric-label">CPU</span>
                <span class="metric-value">${formatPercent(cpuValue)}</span>
              </div>
              <div class="metric-progress">
                <div class="progress-bar ${getProgressColorClass(cpuValue)}" 
                     style="width: ${cpuValue || 0}%"></div>
              </div>
            </div>
            
            <!-- 磁盘使用率 -->
            <div class="mb-3">
              <div class="d-flex justify-content-between mb-1">
                <span class="metric-label">磁盘</span>
                <span class="metric-value">${formatPercent(diskValue)}</span>
              </div>
              <div class="metric-progress">
                <div class="progress-bar ${getProgressColorClass(diskValue)}" 
                     style="width: ${diskValue || 0}%"></div>
              </div>
            </div>
            
            <!-- GPU 使用率（如果有） -->
            ${gpuValue !== null && gpuValue !== undefined ? `
              <div class="mb-3">
                <div class="d-flex justify-content-between mb-1">
                  <span class="metric-label">GPU</span>
                  <span class="metric-value">${formatPercent(gpuValue)}</span>
                </div>
                <div class="metric-progress">
                  <div class="progress-bar ${getProgressColorClass(gpuValue)}" 
                       style="width: ${gpuValue || 0}%"></div>
                </div>
              </div>
            ` : ''}
            
            <!-- 最后更新 -->
            <div class="text-muted small">
              <i class="ti ti-clock me-1"></i>更新于 ${formatRelativeTime(latest.ts)}
            </div>
          ` : `
            <!-- 离线状态 -->
            <div class="text-center py-4 text-muted">
              <i class="ti ti-plug-connected-x" style="font-size: 48px; opacity: 0.3;"></i>
              <div class="mt-2">服务器离线</div>
              <div class="small">最后在线: ${formatRelativeTime(server.last_seen_at)}</div>
            </div>
          `}
        </div>
        <div class="card-footer">
          <a href="server-detail.html?id=${server.id}" class="btn btn-primary btn-sm w-100">
            <i class="ti ti-chart-line me-1"></i>查看详情
          </a>
        </div>
      </div>
    </div>
  `;
}

/**
 * 更新统计信息
 */
function updateStats(servers) {
    const total = servers.length;
    const online = servers.filter(s => s.online).length;
    const offline = total - online;
    const failedServices = servers.reduce((sum, s) => {
        return sum + (s.latest?.services_failed_count || 0);
    }, 0);

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-online').textContent = online;
    document.getElementById('stat-offline').textContent = offline;
    document.getElementById('stat-failed-services').textContent = failedServices;
}

/**
 * 更新最后刷新时间
 */
function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('last-update').textContent =
        `最后更新: ${now.toLocaleTimeString('zh-CN')}`;
}

/**
 * 启动自动刷新
 */
function startAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(loadServers, REFRESH_INTERVAL);
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
 * 渲染错误状态
 */
function renderError() {
    const container = document.getElementById('server-cards');
    container.innerHTML = `
    <div class="col-12">
      <div class="empty-state">
        <i class="ti ti-alert-triangle" style="font-size: 64px; color: #d63939;"></i>
        <h3>加载失败</h3>
        <p>无法连接到后端服务</p>
        <button class="btn btn-primary" onclick="loadServers()">
          <i class="ti ti-refresh me-1"></i>重试
        </button>
      </div>
    </div>
  `;
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
        loadServers();
        startAutoRefresh();
    }
});
