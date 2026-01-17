/**
 * 事件页逻辑
 * 
 * 负责展示事件时间线和过滤功能
 */

let events = [];
let filteredEvents = [];
let displayCount = 50;
let currentFilter = '';

/**
 * 初始化页面
 */
async function init() {
    // 绑定过滤器事件
    document.getElementById('type-filter').addEventListener('change', (e) => {
        currentFilter = e.target.value;
        filterEvents();
        renderEvents();
    });

    // 加载事件列表
    await loadEvents();
}

/**
 * 加载事件列表
 */
async function loadEvents() {
    try {
        events = await api.getEvents(500); // 获取最近 500 条事件
        filterEvents();
        renderEvents();
    } catch (error) {
        console.error('Failed to load events:', error);
        showToast(`加载失败: ${error.message}`, 'danger');
        renderError();
    }
}

/**
 * 过滤事件
 */
function filterEvents() {
    if (!currentFilter) {
        filteredEvents = [...events];
    } else {
        filteredEvents = events.filter(e => e.type === currentFilter);
    }
    displayCount = 50; // 重置显示数量
}

/**
 * 渲染事件列表
 */
function renderEvents() {
    const container = document.getElementById('events-timeline');
    const loadMoreSection = document.getElementById('load-more-section');

    if (!filteredEvents || filteredEvents.length === 0) {
        container.innerHTML = `
      <div class="empty-state">
        <i class="ti ti-bell-off" style="font-size: 64px; opacity: 0.5;"></i>
        <h3>暂无事件</h3>
        <p>${currentFilter ? '没有符合筛选条件的事件' : '还没有记录任何事件'}</p>
      </div>
    `;
        loadMoreSection.style.display = 'none';
        return;
    }

    const eventsToShow = filteredEvents.slice(0, displayCount);

    container.innerHTML = eventsToShow.map(event => renderEventItem(event)).join('');

    // 显示/隐藏加载更多按钮
    loadMoreSection.style.display = displayCount < filteredEvents.length ? 'block' : 'none';
}

/**
 * 渲染单个事件项
 */
function renderEventItem(event) {
    const iconMap = {
        server_down: { icon: 'ti-server-off', color: 'danger' },
        server_up: { icon: 'ti-server', color: 'success' },
        service_failed: { icon: 'ti-alert-triangle', color: 'warning' },
        service_recovered: { icon: 'ti-circle-check', color: 'success' }
    };

    const typeLabels = {
        server_down: '服务器离线',
        server_up: '服务器上线',
        service_failed: '服务异常',
        service_recovered: '服务恢复'
    };

    const { icon, color } = iconMap[event.type] || { icon: 'ti-info-circle', color: 'info' };
    const typeLabel = typeLabels[event.type] || event.type;

    return `
    <div class="event-item ${event.type}">
      <div class="d-flex gap-3">
        <div class="flex-shrink-0">
          <span class="avatar avatar-sm bg-${color}-lt">
            <i class="${icon} text-${color}"></i>
          </span>
        </div>
        <div class="flex-grow-1">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <span class="badge bg-${color}-lt text-${color} mb-1">${typeLabel}</span>
              <div class="event-message">${escapeHtml(event.message)}</div>
              <div class="text-muted small mt-1">
                <i class="ti ti-server me-1"></i>${escapeHtml(event.server_name || `服务器 #${event.server_id}`)}
              </div>
            </div>
            <div class="event-time text-end">
              <div>${formatTime(event.ts)}</div>
              <div class="text-muted small">${formatRelativeTime(event.ts)}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

/**
 * 加载更多
 */
function loadMore() {
    displayCount += 50;
    renderEvents();
}

/**
 * 渲染错误状态
 */
function renderError() {
    const container = document.getElementById('events-timeline');
    container.innerHTML = `
    <div class="empty-state">
      <i class="ti ti-alert-triangle" style="font-size: 64px; color: #d63939;"></i>
      <h3>加载失败</h3>
      <p>无法连接到后端服务</p>
      <button class="btn btn-primary" onclick="loadEvents()">
        <i class="ti ti-refresh me-1"></i>重试
      </button>
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
