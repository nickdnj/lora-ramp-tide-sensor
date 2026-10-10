# Host tests for the portable firmware core. Usage: make -C firmware/test/host
CXX ?= c++
CXXFLAGS ?= -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
CORE := $(HERE)../../lib/tidecore/src
VECTORS := $(abspath $(HERE)../../../tests/vectors)
BUILD := $(HERE)build
SRCS := $(CORE)/payload.cpp $(CORE)/stats.cpp $(CORE)/power_logic.cpp $(CORE)/cycle.cpp $(HERE)test_tidecore.cpp

.PHONY: test clean
test: $(BUILD)/test_tidecore
	$(BUILD)/test_tidecore $(VECTORS)

$(BUILD)/test_tidecore: $(SRCS) $(wildcard $(CORE)/*.h) $(HERE)minijson.h
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -I$(CORE) -I$(HERE) $(SRCS) -o $@

clean:
	rm -rf $(BUILD)
