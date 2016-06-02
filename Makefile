SRCS    = $(shell ls *.py)
TARGETS = $(SRCS:.py=.pyc)

all: $(TARGETS)
	@echo
	@echo "This Makefile is for syntax checking only."
	@echo "For configuring collectd, please see /etc/collectd/collectd.conf."

%.pyc: %.py
	python -m py_compile $<

.PHONY: clean

clean:
	rm -f *.pyc
