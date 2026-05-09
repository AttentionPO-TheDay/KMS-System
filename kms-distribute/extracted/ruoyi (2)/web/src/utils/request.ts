import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Session } from '/@/utils/storage';
import qs from 'qs';

// 配置新建一个 axios 实例
const service: AxiosInstance = axios.create({
	baseURL: import.meta.env.VITE_API_URL,
	timeout: 50000,
	headers: { 'Content-Type': 'application/json' },
	paramsSerializer: {
		serialize(params) {
			return qs.stringify(params, { allowDots: true });
		},
	},
});

// 添加请求拦截器
service.interceptors.request.use(
	(config: AxiosRequestConfig) => {
		// 在发送请求之前做些什么 token
		if (Session.get('token')) {
			config.headers!['Authorization'] = `JWT ${Session.get('token')}`;
		}
		return config;
	},
	(error) => {
		// 对请求错误做些什么
		return Promise.reject(error);
	}
);

// 添加响应拦截器
service.interceptors.response.use(
	(response) => {
		// 对响应数据做点什么
		const res = response.data;
		if (res.code && res.code !== 2000 && res.code !== 0) {
			// 检查是否是白名单API，白名单API的4000错误不触发退出登录
			const url = response.config?.url || '';
			const isWhitelistApi = url.includes('/api/system/user/user_info/') ||
								   url.includes('/api/system/menu/web_router/') ||
								   url.includes('/api/system/menu_button/menu_button_all_permission/') ||
								   url.includes('/api/system/operation_log/') ||
								   url.includes('/api/pqkds/stats/') ||
								   url.includes('/api/pqkds/logs/') ||
								   url.includes('/api/pqkds/blockchain-config/') ||
								   url.includes('/api/pqkds/nodes/') ||
								   url.includes('/api/pqkds/session-keys/') ||
								   url.includes('/api/pqkds/messages/') ||
								   url.includes('/api/pqkds/key-pool/') ||
								   url.includes('/generate_falcon_keys/') ||
								   url.includes('/generate_falcon_keys_v2/') ||
								   url.includes('/generate-falcon-keypair/');

			// `token` 过期或者账号已在别处登录
			if ((res.code === 401 || res.code === 4001 || res.code === 4000) && !isWhitelistApi) {
				Session.clear(); // 清除浏览器全部临时缓存
				window.location.href = '/'; // 去登录页
				ElMessageBox.alert('你已被登出，请重新登录', '提示', {})
					.then(() => {})
					.catch(() => {});
			}
			return Promise.reject(res);
		} else {
			return response.data;
		}
	},
	(error) => {
		// 对响应错误做点什么
		if (error.message.indexOf('timeout') != -1) {
			ElMessage.error('网络超时');
		} else if (error.message == 'Network Error') {
			ElMessage.error('网络连接错误');
		} else {
			if (error.response && error.response.data) {
				ElMessage.error(error.response.statusText || '请求失败');
			} else {
				ElMessage.error('接口路径找不到');
			}
		}
		return Promise.reject(error);
	}
);

// 导出 axios 实例
export default service;
