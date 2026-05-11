<template>
	<div class="app-container">
		<el-card class="box-card">
			<template #header>
				<div class="record-header">
					<span>旧版分发记录</span>
					<el-button type="warning" icon="Download" @click="handleExport">导出</el-button>
				</div>
			</template>

			<el-form :model="queryParams" :inline="true" label-width="80px">
				<el-form-item label="用户名">
					<el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
				</el-form-item>
				<el-form-item label="密钥名称">
					<el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="handleQuery" />
				</el-form-item>
				<el-form-item label="分发类型">
					<el-select v-model="queryParams.distributeType" placeholder="请选择分发类型" clearable>
						<el-option label="初始分发" value="1" />
						<el-option label="更新分发" value="2" />
						<el-option label="回收后补发" value="3" />
					</el-select>
				</el-form-item>
				<el-form-item label="分发状态">
					<el-select v-model="queryParams.distributeStatus" placeholder="请选择分发状态" clearable>
						<el-option label="待分发" value="0" />
						<el-option label="分发中" value="1" />
						<el-option label="分发成功" value="2" />
						<el-option label="分发失败" value="3" />
					</el-select>
				</el-form-item>
				<el-form-item>
					<el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
					<el-button icon="Refresh" @click="resetQuery">重置</el-button>
				</el-form-item>
			</el-form>

			<el-table v-loading="loading" :data="recordList" style="width: 100%">
				<el-table-column label="记录ID" align="center" prop="recordId" width="90" />
				<el-table-column label="用户名" align="center" prop="userName" width="120" />
				<el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
				<el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
				<el-table-column label="分发类型" align="center" prop="distributeType" width="110">
					<template #default="scope">
						<el-tag :type="getDistributeTypeTag(scope.row.distributeType)">{{ formatDistributeType(scope.row.distributeType) }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column label="分发状态" align="center" prop="distributeStatus" width="110">
					<template #default="scope">
						<el-tag :type="getDistributeStatusTag(scope.row.distributeStatus)">{{ formatDistributeStatus(scope.row.distributeStatus) }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column label="分发时间" align="center" prop="distributeTime" width="180">
					<template #default="scope">{{ formatRecordTime(scope.row.distributeTime) }}</template>
				</el-table-column>
				<el-table-column label="区块链Hash" align="center" prop="chainHash" min-width="200" show-overflow-tooltip />
				<el-table-column label="备注" align="center" prop="remark" min-width="160" show-overflow-tooltip />
				<el-table-column label="操作" align="center" width="100" fixed="right">
					<template #default="scope">
						<el-button link type="primary" @click="handleDetail(scope.row)">详情</el-button>
					</template>
				</el-table-column>
			</el-table>

			<el-pagination
				v-model:current-page="queryParams.pageNum"
				v-model:page-size="queryParams.pageSize"
				:page-sizes="[10, 20, 50, 100]"
				:total="total"
				layout="total, sizes, prev, pager, next, jumper"
				@size-change="getList"
				@current-change="getList"
				style="margin-top: 20px; justify-content: flex-end"
			/>
		</el-card>

		<el-dialog title="分发记录详情" v-model="detailVisible" width="720px" append-to-body>
			<el-descriptions :column="2" border v-if="currentRecord">
				<el-descriptions-item label="记录ID">{{ currentRecord.recordId }}</el-descriptions-item>
				<el-descriptions-item label="密钥ID">{{ currentRecord.keyId }}</el-descriptions-item>
				<el-descriptions-item label="用户名">{{ currentRecord.userName }}</el-descriptions-item>
				<el-descriptions-item label="密钥名称">{{ currentRecord.keyName }}</el-descriptions-item>
				<el-descriptions-item label="加密算法">{{ currentRecord.encrytName }}</el-descriptions-item>
				<el-descriptions-item label="分发类型">
					<el-tag :type="getDistributeTypeTag(currentRecord.distributeType)">{{ formatDistributeType(currentRecord.distributeType) }}</el-tag>
				</el-descriptions-item>
				<el-descriptions-item label="分发状态">
					<el-tag :type="getDistributeStatusTag(currentRecord.distributeStatus)">{{ formatDistributeStatus(currentRecord.distributeStatus) }}</el-tag>
				</el-descriptions-item>
				<el-descriptions-item label="分发时间">{{ formatRecordTime(currentRecord.distributeTime) }}</el-descriptions-item>
				<el-descriptions-item label="区块链Hash" :span="2">{{ currentRecord.chainHash }}</el-descriptions-item>
				<el-descriptions-item label="区块高度">{{ currentRecord.blockHeight }}</el-descriptions-item>
				<el-descriptions-item label="备注" :span="2">{{ currentRecord.remark }}</el-descriptions-item>
			</el-descriptions>
		</el-dialog>
	</div>
</template>

<script lang="ts" setup name="pqkdsRecords">
import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { formatDate } from '/@/utils/formatTime';
import { getKeyDistributeRecord, listKeyDistributeRecord, exportKeyDistributeRecord } from '/@/api/distribute/record';

const loading = ref(false);
const total = ref(0);
const recordList = ref<any[]>([]);
const detailVisible = ref(false);
const currentRecord = ref<any>(null);

const queryParams = reactive({
	pageNum: 1,
	pageSize: 10,
	userName: '',
	keyName: '',
	distributeType: '',
	distributeStatus: '',
});

function getList() {
	loading.value = true;
	listKeyDistributeRecord({ ...queryParams })
		.then((res: any) => {
			recordList.value = res.rows || [];
			total.value = res.total || 0;
		})
		.catch(() => {
			recordList.value = [];
			total.value = 0;
		})
		.finally(() => {
			loading.value = false;
		});
}

function handleQuery() {
	queryParams.pageNum = 1;
	getList();
}

function resetQuery() {
	queryParams.pageNum = 1;
	queryParams.userName = '';
	queryParams.keyName = '';
	queryParams.distributeType = '';
	queryParams.distributeStatus = '';
	getList();
}

function handleDetail(row: any) {
	if (!row.recordId) {
		ElMessage.warning('记录ID为空');
		return;
	}
	getKeyDistributeRecord(row.recordId).then((res: any) => {
		currentRecord.value = res.data;
		detailVisible.value = true;
	});
}

function handleExport() {
	exportKeyDistributeRecord({ ...queryParams }).then((blob: Blob) => {
		const url = window.URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = `key-distribute-record-${Date.now()}.xlsx`;
		link.click();
		window.URL.revokeObjectURL(url);
	});
}

function formatRecordTime(value: string | Date | null | undefined) {
	return value ? formatDate(new Date(value), 'YYYY-mm-dd HH:MM:SS') : '';
}

function formatDistributeType(type: string | number) {
	const value = String(type);
	if (value === '1') return '初始分发';
	if (value === '2') return '更新分发';
	if (value === '3') return '回收后补发';
	return '未知';
}

function formatDistributeStatus(status: string | number) {
	const value = String(status);
	if (value === '0') return '待分发';
	if (value === '1') return '分发中';
	if (value === '2') return '分发成功';
	if (value === '3') return '分发失败';
	return '未知';
}

function getDistributeTypeTag(type: string | number) {
	const value = String(type);
	if (value === '1') return 'success';
	if (value === '2') return 'warning';
	return 'info';
}

function getDistributeStatusTag(status: string | number) {
	const value = String(status);
	if (value === '0') return 'info';
	if (value === '1') return 'primary';
	if (value === '2') return 'success';
	return 'danger';
}

onMounted(getList);
</script>

<style scoped>
.record-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
}
</style>
