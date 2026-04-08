-- post.lua
wrk.method = "POST"
wrk.body   = '{"user": "test", "password": "123456", "encryt_type": "无证书非对称加密", "encryt_name": "SM2", "ua": "04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a"}'
wrk.headers["Content-Type"] = "application/json"
