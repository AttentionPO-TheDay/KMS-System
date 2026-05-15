import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus';
import qs from 'qs';
import { Session } from '/@/utils/storage';

const legacyService: AxiosInstance = axios.create({
	baseURL: import.meta.env.VITE_LEGACY_API_URL || '/distribute-api',
	timeout: 10000,
	headers: { 'Content-Type': 'application/json;charset=utf-8' },
	paramsSerializer: {
		serialize(params) {
			return qs.stringify(params, { allowDots: true });
		},
	},
});

legacyService.interceptors.request.use(
	(config: AxiosRequestConfig) => {
		const token = Session.get('token');
		if (token && config.headers?.isToken !== false) {
			config.headers!['Authorization'] = `Bearer ${token}`;
		}
		return config;
	},
	(error) => Promise.reject(error)
);

legacyService.interceptors.response.use(
	(response) => {
		const res = response.data;
		const code = res.code || 200;
		const msg = res.msg || res.message || '请求失败';

		if (response.request.responseType === 'blob' || response.request.responseType === 'arraybuffer') {
			return res;
		}
		if (code === 401) {
			ElMessageBox.alert('登录状态已过期，请重新登录', '系统提示', {})
				.then(() => {
					Session.clear();
					window.location.href = '/';
				})
				.catch(() => {});
			return Promise.reject(new Error('登录状态已过期'));
		}
		if (code !== 200) {
			ElNotification.error({ title: msg });
			return Promise.reject(new Error(msg));
		}
		return res;
	},
	(error) => {
		let message = error.message;
		if (message === 'Network Error') message = '后端接口连接异常';
		else if (message.includes('timeout')) message = '系统接口请求超时';
		else if (message.includes('Request failed with status code')) message = `系统接口${message.slice(-3)}异常`;
		ElMessage.error(message);
		return Promise.reject(error);
	}
);

export default legacyService;
