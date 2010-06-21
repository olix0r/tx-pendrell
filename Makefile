#
# BSD make(1)-formatted
# 

BUILDDIR ?= build
PYTHON = python
PYTHONPATH ?=
TRIAL_ARGS ?= 
TRIAL = env PYTHONPATH="${BUILDDIR}/lib:${PYTHONPATH}" trial ${TRIAL_ARGS}


build:
	${PYTHON} setup.py build -b ${BUILDDIR}

sdist:
	${PYTHON} setup.py sdist

bdist:
	${PYTHON} setup.py bdist -b ${BUILDDIR}

rpm:
	${PYTHON} setup.py build -b ${BUILDDIR} bdist_rpm

yinst:
	${PYTHON} setup.py build -b ${BUILDDIR} bdist_yinst


test: build
	${TRIAL} pendrell.cases 2>&1 | tee _trial_results

test-agent: build
	${TRIAL} pendrell.cases.test_agent 2>&1 | tee _trial_results.agent

test-auth: build
	${TRIAL} pendrell.cases.test_auth 2>&1 | tee _trial_results.auth

test-jigsaw: build
	${TRIAL} pendrell.cases.test_jigsaw 2>&1 \
		| tee _trial_results.functional

test-functional: build
	${TRIAL} pendrell.cases.test_functional 2>&1 \
		| tee _trial_results.functional

test-transfer: build
	${TRIAL} pendrell.cases._test_transfer \
		2>&1 | tee _trial_results.transfer

test-proxy: build
	${TRIAL} pendrell.cases.test_proxy 2>&1 | tee _trial_results.proxy


clean:
	${PYTHON} setup.py clean -b ${BUILDDIR} -a
	rm -rf _trial_* MANIFEST

