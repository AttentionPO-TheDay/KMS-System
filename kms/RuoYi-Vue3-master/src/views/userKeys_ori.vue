<template>  
  <div class="tabelContainer">
      <!-- <el-badge :value="3" class="item notice">
          <el-button>notices</el-button>
      </el-badge> -->
      <div class="avatar-container">
          <el-dropdown @command="handleCommand" class="right-menu-item hover-effect" trigger="click">
              <div class="avatar-wrapper">
                  <img :src="userStore.avatar" class="user-avatar" />
                  <el-icon><caret-bottom /></el-icon>
              </div>
              <template #dropdown>
                  <el-dropdown-menu>
                      <router-link to="/user/profile">
                          <el-dropdown-item>个人中心</el-dropdown-item>
                      </router-link>
                      <el-dropdown-item command="setLayout" v-if="settingsStore.showSettings">
                          <span>布局设置</span>
                      </el-dropdown-item>
                      <el-dropdown-item divided command="logout">
                          <span>退出登录</span>
                      </el-dropdown-item>
                  </el-dropdown-menu>
              </template>
          </el-dropdown>
      </div>
      <h1>用户系统</h1>
      <el-button type="primary" @click="createKey">密钥生成申请</el-button>
      <el-button type="primary" plain>密钥分发申请</el-button>
      <el-button type="primary" plain>密钥更新申请</el-button>
      <el-button type="primary" plain>启用密钥自动更新申请</el-button>
      <el-button type="primary" plain>关闭密钥自动更新申请</el-button>
      <el-button type="primary" plain>密钥回收申请</el-button>
      <el-button type="primary" plain>密钥恢复申请</el-button>
   
      <el-table class="table" border :data="tableData" style="width: 100%">
        <el-table-column type="selection" width="55" />
        <el-table-column property="use" label="加密算法类型"/>
        <el-table-column property="use" label="加密算法名称"/>
        <el-table-column property="name" label="密钥名称"/>
        <el-table-column property="name" label="密钥用途"/>
        <el-table-column property="date" label="创建时间" />
        <el-table-column property="date" label="更新时间" />
        <el-table-column property="alternate" label="密钥更新状态" >
          <template #default="scope">
            <ElSwitch v-model="scope.row.alternate" />
          </template>
        </el-table-column>

        <el-table-column label="操作" fixed="right" >
        <template #default="scope">
          <!-- <el-button link type="primary" size="small" @click="open(scope.$index, scope.row)">启用</el-button>
          <el-button link type="primary" size="small" @click="disable(scope.$index, scope.row)">禁用</el-button> -->
          <el-button link type="danger" size="small" @click="deleteRow(scope.$index, scope.row)">回收申请</el-button>
        </template>
      </el-table-column>
    </el-table>
    <create-key-dialog ref="createKeyDialogRef"></create-key-dialog>
  </div>
  </template>
  
  <script setup>
  import { reactive,ref } from 'vue';
  import createKeyDialog from '../components/createKeyDialog.vue';
  import { ElMessage, ElMessageBox } from 'element-plus'
  import useAppStore from '@/store/modules/app'
  import useUserStore from '@/store/modules/user'
  import useSettingsStore from '@/store/modules/settings'

  const createKeyDialogRef = ref()
  const tableData = reactive([
    {
     name:'111',
     date:'2024-05-03',
     use:'对称加解密',
     source:'KMS',
     tag:'ffff.ssss',
     alternate:true,
     status:'0'
    },
    {
     name:'222',
     date:'2024-05-03',
     use:'混合加解密',
     source:'KMS',
     tag:'ffff.ssss',
     alternate:true,
     status:'0'
    },
    {
     name:'333',
     date:'2024-05-03',
     use:'非对称加解密',
     source:'KMS',
     tag:'ffff.ssss',
     alternate:false,
     status:'0'
    },
    
  ]);
  
  const open = (index, row)=>{
    tableData[index].status = '1'
  }
  const disable = (index, row)=>{
    tableData[index].status = '2'
  }
  // 从数据源中移除对应行
  const deleteRow = (index, row) => {
    ElMessageBox.confirm(
      '确定删除当前行吗？',
      '提示',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
      .then(() => {
        tableData.splice(index, 1);
        ElMessage({
          type: 'success',
          message: '删除成功',
        })
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '取消删除',
        })
      })
  };
  
  // 打开创建密钥的弹窗
  const createKey = () => {
    createKeyDialogRef.value.createDialogVisible = true;  
  };

  const appStore = useAppStore()
  const userStore = useUserStore()
  const settingsStore = useSettingsStore()

  function handleCommand(command) {
    switch (command) {
      case "setLayout":
        setLayout();
        break;
      case "logout":
        logout();
        break;
      default:
        break;
    }
  }

  function logout() {
    ElMessageBox.confirm('确定注销并退出系统吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      userStore.logOut().then(() => {
        location.href = '/index';
      })
    }).catch(() => { });
  }

  const emits = defineEmits(['setLayout'])
  function setLayout() {
    emits('setLayout');
  }
  </script>
  <style  scoped>
  ::v-deep .el-table .cell{
    font-size:18px;
  }
  ::v-deep th .cell{
    font-size:30px;
    font-weight: bold;
  }
  ::v-deep .el-button>span{
    font-size:16px;
  }
  ::v-deep .el-tag__content{
    font-size:16px;
  }
  .tabelContainer{
    width:100%;
  }
  .table{
    margin-top:20px;
  }
  h1{
      text-align: center;
      margin:20px 0;
  }
  .notice{
      position: relative;
      display: inline-block;
  }
  .avatar-container {
      position: relative;
      display: inline-block;
      float: right;
      margin-left: 10px; /* 调整与notices的间距 */
  }
  .avatar-container .avatar-wrapper {
      margin-top: 5px;
      position: relative;
  }
  .avatar-container .avatar-wrapper .user-avatar {
      cursor: pointer;
      width: 40px;
      height: 40px;
      border-radius: 10px;
  }
  .avatar-container .avatar-wrapper i {
      cursor: pointer;
      position: absolute;
      right: -20px;
      top: 25px;
      font-size: 12px;
  }
  </style>