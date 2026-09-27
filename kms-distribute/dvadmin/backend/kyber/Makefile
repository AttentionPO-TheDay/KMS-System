CC ?= gcc
CFLAGS = -Wall -Wextra -O2 -I.
LDFLAGS = -L./ref

# Kyber库文件
KYBER_LIB = ref/libpqcrystals_kyber768_ref.so ref/libpqcrystals_fips202_ref.so

.PHONY: all clean kyber_lib run run_device

all: kyber_lib rlwe_key_exchange rlwe_device_exchange

# 编译Kyber库
kyber_lib:
	$(MAKE) -C ref shared KYBER_K=3

# 编译密钥交换示例程序
rlwe_key_exchange: rlwe_key_exchange.c $(KYBER_LIB)
	$(CC) $(CFLAGS) -o $@ $< $(KYBER_LIB) $(LDFLAGS)

# 编译设备间密钥交换示例程序
rlwe_device_exchange: rlwe_device_exchange.c $(KYBER_LIB)
	$(CC) $(CFLAGS) -o $@ $< $(KYBER_LIB) $(LDFLAGS)

clean:
	$(MAKE) -C ref clean
	rm -f rlwe_key_exchange rlwe_device_exchange
	rm -f *.key *.bin

# 运行基本示例
run: all
	LD_LIBRARY_PATH=./ref ./rlwe_key_exchange

# 运行设备间通信示例
run_device: all
	@echo "模拟Alice设备生成密钥..."
	LD_LIBRARY_PATH=./ref ./rlwe_device_exchange alice
	@echo "\n模拟Bob设备生成共享密钥..."
	LD_LIBRARY_PATH=./ref ./rlwe_device_exchange bob
	@echo "\n模拟Alice设备恢复并验证共享密钥..."
	LD_LIBRARY_PATH=./ref ./rlwe_device_exchange verify 