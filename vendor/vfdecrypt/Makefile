PREFIX=$(shell brew --prefix openssl@3)

ifeq ($(PREFIX),)

else
CFLAGS=-I$(PREFIX)/include/
LDFLAGS=-L$(PREFIX)/lib/
endif

CFLAGS += -Wno-deprecated-declarations

linux:
	cc -o vfdecrypt vfdecrypt.c -lcrypto $(LDFLAGS) $(CFLAGS)
install:
	cp ./vfdecrypt /usr/local/bin
	ldconfig
uninstall:
	rm -rf /usr/local/bin/vfdecrypt
clean:
	rm -rf ./vfdecrypt
