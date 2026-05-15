import qs from 'qs';
import legacyRequest from '/@/utils/legacyRequest';

export function listKeyDistributeRecord(params?: any) {
	return legacyRequest({
		url: '/distribute/record/list',
		method: 'get',
		params,
	});
}

export function getKeyDistributeRecord(recordId: string | number) {
	return legacyRequest({
		url: `/distribute/record/${recordId}`,
		method: 'get',
	});
}

export function exportKeyDistributeRecord(params?: any) {
	return legacyRequest({
		url: '/distribute/record/export',
		method: 'post',
		data: params,
		responseType: 'blob',
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		transformRequest: [(data) => qs.stringify(data)],
	});
}
