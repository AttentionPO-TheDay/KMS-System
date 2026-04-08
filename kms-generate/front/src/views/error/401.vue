<template>
  <div class="wscn-http404-container">
    <div class="wscn-http404">
      <div class="pic-401">
        <div class="pic-401__parent">401</div>
      </div>
      <div class="bullshit">
        <div class="bullshit__oops">401!</div>
        <div class="bullshit__headline">抱歉，您没有访问权限</div>
        <div class="bullshit__info">请联系管理员为您分配权限。</div>
        <a href="/" class="bullshit__return-home">返回首页</a>
      </div>
    </div>
  </div>
</template>

<script>
export default { name: 'Page401' }
</script>

<style lang="scss" scoped>
.wscn-http404-container { transform: translate(-50%, -50%); position: absolute; top: 40%; left: 50% }
.wscn-http404 { position: relative; width: 1200px; padding: 0 50px; overflow: hidden }
.pic-401 { position: relative; float: left; width: 600px; overflow: hidden }
.pic-401__parent { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 320px; border-radius: 24px; font-size: 120px; font-weight: 700; color: #1482f0; background: linear-gradient(135deg, #eef6ff, #dcecff) }
.bullshit { position: relative; float: left; width: 300px; padding: 30px 0; overflow: hidden }
.bullshit__oops { font-size: 32px; font-weight: bold; line-height: 40px; color: #1482f0; opacity: 0; margin-bottom: 20px; animation-name: slideUp; animation-duration: 0.5s; animation-fill-mode: forwards }
.bullshit__headline { font-size: 20px; line-height: 24px; color: #222; font-weight: bold; margin-bottom: 10px; animation-name: slideUp; animation-duration: 0.5s; animation-delay: 0.1s; animation-fill-mode: forwards }
.bullshit__info { font-size: 13px; line-height: 21px; color: grey; margin-bottom: 30px; animation-name: slideUp; animation-duration: 0.5s; animation-delay: 0.2s; animation-fill-mode: forwards }
.bullshit__return-home { display: block; float: none; width: 110px; height: 36px; margin: 0 auto; line-height: 36px; color: #ffffff; background: #1482f0; border-radius: 100px; font-size: 14px; text-align: center; text-decoration: none; animation-name: slideUp; animation-duration: 0.5s; animation-delay: 0.3s; animation-fill-mode: forwards }
@keyframes slideUp { 0% { transform: translateY(60px); opacity: 0 } 100% { transform: translateY(0); opacity: 1 } }
</style>
