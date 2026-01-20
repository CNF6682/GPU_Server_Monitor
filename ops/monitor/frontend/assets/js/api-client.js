/**
 * API 客户端封装
 * 
 * 封装所有与 Aggregator API 的通信
 */

class APIClient {
    constructor(baseUrl = API_BASE) {
        this.baseUrl = baseUrl;
    }

    /**
     * 通用请求方法
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        try {
            const response = await fetch(url, { ...defaultOptions, ...options });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new APIError(
                    errorData.detail || `HTTP ${response.status}`,
                    response.status
                );
            }

            return await response.json();
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }
            throw new APIError(`网络错误: ${error.message}`, 0);
        }
    }

    // =========================================================================
    // 服务器相关 API
    // =========================================================================

    /**
     * 获取所有服务器及最新状态
     */
    async getServers() {
        return this.request('/api/servers');
    }

    /**
     * 获取单个服务器详情
     */
    async getServer(serverId) {
        return this.request(`/api/servers/${serverId}`);
    }

    /**
     * 创建服务器
     */
    async createServer(data) {
        return this.request('/api/servers', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    /**
     * 更新服务器
     */
    async updateServer(serverId, data) {
        return this.request(`/api/servers/${serverId}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    /**
     * 删除服务器
     */
    async deleteServer(serverId) {
        return this.request(`/api/servers/${serverId}`, {
            method: 'DELETE',
        });
    }

    /**
     * 发现服务（服务发现）
     */
    async discoverServices(serverId) {
        return this.request(`/api/servers/${serverId}/services/catalog`);
    }

    // =========================================================================
    // 时间序列 API
    // =========================================================================

    /**
     * 获取时间序列数据
     * @param {number} serverId - 服务器 ID
     * @param {string} metric - 指标名称 (cpu_pct|disk_used_pct|gpu_util_pct)
     * @param {string} from - 起始时间 (ISO 8601)
     * @param {string} to - 结束时间 (ISO 8601)
     * @param {string} agg - 聚合类型 (avg|max)
     */
    async getTimeseries(serverId, metric, from, to, agg = 'avg') {
        const params = new URLSearchParams({ metric, from, to, agg });
        return this.request(`/api/servers/${serverId}/timeseries?${params}`);
    }

    // =========================================================================
    // 事件 API
    // =========================================================================

    /**
     * 获取事件列表
     * @param {number} limit - 返回数量限制
     */
    async getEvents(limit = 200) {
        return this.request(`/api/events?limit=${limit}`);
    }

    // =========================================================================
    // 历史数据 API
    // =========================================================================

    /**
     * 获取按小时聚合的历史数据
     * @param {URLSearchParams|Object} params - 查询参数
     */
    async getHourlyHistory(params) {
        const qs = params instanceof URLSearchParams ? params.toString() : new URLSearchParams(params).toString();
        return this.request(`/api/history/hourly?${qs}`);
    }

    // =========================================================================
    // 代理转发 API
    // =========================================================================

    /**
     * 获取代理配置和状态
     * @param {number} serverId 
     */
    async getProxyConfig(serverId) {
        return this.request(`/api/servers/${serverId}/proxy`);
    }

    /**
     * 更新代理配置或控制代理状态
     * @param {number} serverId 
     * @param {Object} config - 代理配置对象
     * @param {string|null} action - 'start' | 'stop' | null
     */
    async updateProxyConfig(serverId, config, action = null) {
        return this.request(`/api/servers/${serverId}/proxy`, {
            method: 'PUT',
            body: JSON.stringify({ config, action }),
        });
    }
}

/**
 * 自定义 API 错误类
 */
class APIError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'APIError';
        this.status = status;
    }
}

// 创建全局 API 客户端实例
const api = new APIClient();

// =========================================================================
// 工具函数
// =========================================================================

/**
 * 格式化字节数
 */
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0 || bytes === null || bytes === undefined) return '0 B';

    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];

    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * 格式化百分比
 */
function formatPercent(value, decimals = 1) {
    if (value === null || value === undefined) return '-';
    return value.toFixed(decimals) + '%';
}

/**
 * 格式化时间
 */
function formatTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
}

/**
 * 格式化相对时间
 */
function formatRelativeTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return `${diffSec} 秒前`;
    if (diffMin < 60) return `${diffMin} 分钟前`;
    if (diffHour < 24) return `${diffHour} 小时前`;
    return `${diffDay} 天前`;
}

/**
 * 获取进度条颜色类
 */
function getProgressColorClass(value) {
    if (value === null || value === undefined) return 'low';
    if (value < 50) return 'low';
    if (value < 75) return 'medium';
    if (value < 90) return 'high';
    return 'critical';
}

/**
 * 判断服务器是否在线
 */
function isServerOnline(lastSeenAt) {
    if (!lastSeenAt) return false;
    const lastSeen = new Date(lastSeenAt);
    const now = new Date();
    const diffSec = (now - lastSeen) / 1000;
    return diffSec < OFFLINE_THRESHOLD;
}

/**
 * 显示 Toast 通知
 */
function showToast(message, type = 'info') {
    // 创建 toast 容器（如果不存在）
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
        document.body.appendChild(container);
    }

    // 创建 toast 元素
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible`;
    toast.style.cssText = 'min-width: 300px; margin-bottom: 10px; animation: slideIn 0.3s ease;';
    toast.innerHTML = `
    ${message}
    <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
  `;

    container.appendChild(toast);

    // 3 秒后自动消失
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }
    }, 3000);
}

// 添加 toast 动画样式
const toastStyles = document.createElement('style');
toastStyles.textContent = `
  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  @keyframes slideOut {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(100%); opacity: 0; }
  }
`;
document.head.appendChild(toastStyles);
