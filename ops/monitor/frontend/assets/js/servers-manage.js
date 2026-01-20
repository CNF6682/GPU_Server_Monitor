/**
 * 服务器管理页逻辑
 * 
 * 负责服务器的添加、编辑、删除功能
 */

let servers = [];
let editingServerId = null;
let serverModal = null;
let deleteModal = null;

/**
 * 初始化页面
 */
async function init() {
  // 初始化 Bootstrap 模态框
  serverModal = new bootstrap.Modal(document.getElementById('server-modal'));
  deleteModal = new bootstrap.Modal(document.getElementById('delete-modal'));

  // 加载服务器列表
  await loadServers();
}

/**
 * 加载服务器列表
 */
async function loadServers() {
  try {
    servers = await api.getServers();
    renderServersTable(servers);
  } catch (error) {
    console.error('Failed to load servers:', error);
    showToast(`加载失败: ${error.message}`, 'danger');
    renderError();
  }
}

/**
 * 渲染服务器表格
 */
function renderServersTable(servers) {
  const tbody = document.getElementById('servers-tbody');

  if (!servers || servers.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="text-center py-4">
          <div class="empty-state">
            <i class="ti ti-server-off" style="font-size: 48px; opacity: 0.5;"></i>
            <h3>暂无服务器</h3>
            <p>点击右上角"添加服务器"开始监控</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = servers.map(server => renderServerRow(server)).join('');
}

/**
 * 渲染单行服务器数据
 */
function renderServerRow(server) {
  const online = server.online;
  const services = server.services ? JSON.parse(server.services) : [];

  return `
    <tr>
      <td>
        <div class="d-flex align-items-center">
          <span class="status-indicator ${online ? 'online' : 'offline'}"></span>
          <div>
            <div class="font-weight-medium">${escapeHtml(server.name)}</div>
            ${!server.enabled ? '<span class="badge bg-secondary">已禁用</span>' : ''}
          </div>
        </div>
      </td>
      <td class="text-muted">
        ${escapeHtml(server.host)}:${server.agent_port}
      </td>
      <td>
        ${online
      ? '<span class="badge bg-success">在线</span>'
      : '<span class="badge bg-danger">离线</span>'
    }
      </td>
      <td class="text-muted">
        ${formatRelativeTime(server.last_seen_at)}
      </td>
      <td>
        ${services.length > 0
      ? services.slice(0, 3).map(s => `<span class="badge bg-blue-lt me-1">${escapeHtml(s)}</span>`).join('')
      + (services.length > 3 ? `<span class="badge bg-secondary">+${services.length - 3}</span>` : '')
      : '<span class="text-muted">-</span>'
    }
      </td>
      <td>
        <div class="btn-group">
          <button class="btn btn-sm btn-ghost-primary" onclick="openEditModal(${server.id})" title="编辑">
            <i class="ti ti-edit"></i>
          </button>
          <button class="btn btn-sm btn-ghost-danger" onclick="openDeleteModal(${server.id})" title="删除">
            <i class="ti ti-trash"></i>
          </button>
        </div>
      </td>
    </tr>
  `;
}

/**
 * 打开添加模态框
 */
function openAddModal() {
  editingServerId = null;
  document.getElementById('modal-title').textContent = '添加服务器';
  document.getElementById('server-form').reset();
  document.getElementById('server-id').value = '';
  document.getElementById('server-port').value = '9109';
  document.getElementById('server-enabled').checked = true;
  document.getElementById('discover-section').style.display = 'none';
  document.getElementById('discovered-services').innerHTML =
    '<span class="text-muted">点击"发现服务"按钮获取可监控的服务列表</span>';

  // 重置代理配置
  resetProxyForm();
}

/**
 * 打开编辑模态框
 */
async function openEditModal(serverId) {
  // 优先使用最新详情（包含 token），若失败回退本地缓存
  let server = servers.find(s => s.id === serverId);
  try {
    server = await api.getServer(serverId);
  } catch (err) {
    console.warn('Failed to fetch server detail, fallback to cached list:', err);
  }
  if (!server) return;

  editingServerId = serverId;
  document.getElementById('modal-title').textContent = '编辑服务器';
  document.getElementById('server-id').value = server.id;
  document.getElementById('server-name').value = server.name;
  document.getElementById('server-host').value = server.host;
  document.getElementById('server-port').value = server.agent_port;
  document.getElementById('server-token').value = server.token || '';
  // 后端返回可能是 bool 或 0/1，统一强制为 true/false，默认启用
  document.getElementById('server-enabled').checked = server.enabled === undefined ? true : !!server.enabled;

  // 解析服务列表
  const services = server.services ? JSON.parse(server.services) : [];
  document.getElementById('server-services').value = services.join('\n');

  // 显示服务发现区域
  document.getElementById('discover-section').style.display = 'block';

  // 加载代理配置
  await loadProxyConfig(serverId);

  serverModal.show();
}

/**
 * 重置代理表单
 */
function resetProxyForm() {
  document.getElementById('proxy-enabled').checked = false;
  document.getElementById('proxy-listen-port').value = '8080';
  document.getElementById('proxy-center-port').value = '7879';
  document.getElementById('proxy-ssh-host').value = '';
  document.getElementById('proxy-ssh-port').value = '22';
  document.getElementById('proxy-ssh-user').value = '';
  document.getElementById('proxy-identity-file').value = '';
  document.getElementById('proxy-strict-host-check').checked = true;
  document.getElementById('proxy-auto-start').checked = false;
}

/**
 * 加载代理配置
 */
async function loadProxyConfig(serverId) {
  resetProxyForm(); // 先重置
  try {
    const response = await api.getProxyConfig(serverId);
    // response 结构预期: { config: {...}, status: {...} }
    // 注意：如果还未配置，config 可能为 null 或默认值
    const config = response.config || {};

    if (config.enabled) document.getElementById('proxy-enabled').checked = true;
    if (config.server_listen_port) document.getElementById('proxy-listen-port').value = config.server_listen_port;
    if (config.center_proxy_port) document.getElementById('proxy-center-port').value = config.center_proxy_port;
    if (config.center_ssh_host) document.getElementById('proxy-ssh-host').value = config.center_ssh_host;
    if (config.center_ssh_port) document.getElementById('proxy-ssh-port').value = config.center_ssh_port;
    if (config.center_ssh_user) document.getElementById('proxy-ssh-user').value = config.center_ssh_user;
    if (config.identity_file) document.getElementById('proxy-identity-file').value = config.identity_file;
    if (config.strict_host_key_checking !== undefined) document.getElementById('proxy-strict-host-check').checked = config.strict_host_key_checking;
    if (config.auto_start) document.getElementById('proxy-auto-start').checked = true;

  } catch (error) {
    console.warn('Failed to load proxy config (might not be configured yet):', error);
    // 忽略错误，可能是 404 或未配置
  }
}

/**
 * 保存服务器
 */
async function saveServer() {
  // 收集表单数据
  const name = document.getElementById('server-name').value.trim();
  const host = document.getElementById('server-host').value.trim();
  const port = parseInt(document.getElementById('server-port').value) || 9109;
  const token = document.getElementById('server-token').value.trim();
  const enabled = document.getElementById('server-enabled').checked;
  const servicesText = document.getElementById('server-services').value.trim();
  const services = servicesText ? servicesText.split('\n').map(s => s.trim()).filter(s => s) : [];

  // 收集代理配置
  const proxyConfig = {
    enabled: document.getElementById('proxy-enabled').checked,
    server_listen_port: parseInt(document.getElementById('proxy-listen-port').value) || 8080,
    center_proxy_port: parseInt(document.getElementById('proxy-center-port').value) || 7879,
    center_ssh_host: document.getElementById('proxy-ssh-host').value.trim(),
    center_ssh_port: parseInt(document.getElementById('proxy-ssh-port').value) || 22,
    center_ssh_user: document.getElementById('proxy-ssh-user').value.trim(),
    identity_file: document.getElementById('proxy-identity-file').value.trim(),
    strict_host_key_checking: document.getElementById('proxy-strict-host-check').checked,
    auto_start: document.getElementById('proxy-auto-start').checked
  };

  // 验证基本信息
  if (!name || !host || !token) {
    showToast('请填写必填字段', 'warning');
    return;
  }

  const data = {
    name,
    host,
    agent_port: port,
    token,
    services,
    enabled
  };

  try {
    let serverId = editingServerId;

    if (editingServerId) {
      // 更新基本信息
      await api.updateServer(editingServerId, data);
      showToast('服务器基本信息已更新', 'success');
    } else {
      // 创建
      const newServer = await api.createServer(data);
      serverId = newServer.id; // 假设返回对象包含 id
      showToast('服务器已添加', 'success');
    }

    // 保存代理配置
    // 只有当启用了代理或填写了关键信息时才保存，或者总是保存？
    // 这里选择总是保存当前表单状态
    if (serverId) {
      await api.updateProxyConfig(serverId, proxyConfig, null);
    }

    serverModal.hide();
    await loadServers();
  } catch (error) {
    console.error('Failed to save server:', error);
    showToast(`保存失败: ${error.message}`, 'danger');
  }
}

/**
 * 打开删除确认模态框
 */
function openDeleteModal(serverId) {
  const server = servers.find(s => s.id === serverId);
  if (!server) return;

  document.getElementById('confirm-delete-btn').onclick = async () => {
    await deleteServer(serverId);
  };

  deleteModal.show();
}

/**
 * 删除服务器
 */
async function deleteServer(serverId) {
  try {
    await api.deleteServer(serverId);
    showToast('服务器已删除', 'success');
    deleteModal.hide();
    await loadServers();
  } catch (error) {
    console.error('Failed to delete server:', error);
    showToast(`删除失败: ${error.message}`, 'danger');
  }
}

/**
 * 生成随机 Token
 */
function generateToken() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let token = '';
  for (let i = 0; i < 32; i++) {
    token += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  document.getElementById('server-token').value = token;
}

/**
 * 发现服务
 */
async function discoverServices() {
  const serverId = editingServerId;
  if (!serverId) {
    showToast('请先保存服务器后再发现服务', 'warning');
    return;
  }

  const container = document.getElementById('discovered-services');
  container.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm"></div> 正在发现服务...</div>';

  try {
    const services = await api.discoverServices(serverId);

    if (!services || services.length === 0) {
      container.innerHTML = '<span class="text-muted">未发现可监控的服务</span>';
      return;
    }

    container.innerHTML = `
      <div class="row g-2">
        ${services.map(svc => `
          <div class="col-md-6 col-lg-4">
            <label class="form-check">
              <input type="checkbox" class="form-check-input discovered-service" 
                     value="${escapeHtml(svc.name)}">
              <span class="form-check-label">
                ${escapeHtml(svc.name)}
                <span class="badge ${svc.active_state === 'active' ? 'bg-green-lt' : 'bg-secondary'}">
                  ${svc.active_state}
                </span>
              </span>
            </label>
          </div>
        `).join('')}
      </div>
      <div class="mt-3">
        <button type="button" class="btn btn-sm btn-primary" onclick="applyDiscoveredServices()">
          <i class="ti ti-check me-1"></i>应用选中的服务
        </button>
      </div>
    `;
  } catch (error) {
    console.error('Failed to discover services:', error);
    container.innerHTML = `<span class="text-danger">发现服务失败: ${error.message}</span>`;
  }
}

/**
 * 应用发现的服务
 */
function applyDiscoveredServices() {
  const checkboxes = document.querySelectorAll('.discovered-service:checked');
  const services = Array.from(checkboxes).map(cb => cb.value);

  // 添加到服务列表
  const textarea = document.getElementById('server-services');
  const existingServices = textarea.value.trim()
    ? textarea.value.trim().split('\n').map(s => s.trim())
    : [];

  // 合并并去重
  const allServices = [...new Set([...existingServices, ...services])];
  textarea.value = allServices.join('\n');

  showToast(`已添加 ${services.length} 个服务`, 'success');
}

/**
 * 渲染错误状态
 */
function renderError() {
  const tbody = document.getElementById('servers-tbody');
  tbody.innerHTML = `
    <tr>
      <td colspan="6" class="text-center py-4">
        <div class="empty-state">
          <i class="ti ti-alert-triangle" style="font-size: 48px; color: #d63939;"></i>
          <h3>加载失败</h3>
          <p>无法连接到后端服务</p>
          <button class="btn btn-primary" onclick="loadServers()">
            <i class="ti ti-refresh me-1"></i>重试
          </button>
        </div>
      </td>
    </tr>
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
