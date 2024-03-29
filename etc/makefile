include $(dir $(lastword $(MAKEFILE_LIST)))/makefile.ext

PLATFORM    := $(shell uname)

NOT_FOUND_P3_CONFIG := $(shell which python3-config 2> /dev/null 1> /dev/null; echo $$?)

ifeq ($(NOT_FOUND_P3_CONFIG),0)
  PYTHON_CONFIG := $(shell which python3-config)
else
  PYTHON_CONFIG := $(shell find /usr/bin -name python3*config | head -1)
endif

SRCDIR       = .
CXX          = c++
LDFLAGS_Darwin = -mmacosx-version-min=10.6
LDFLAGS_Linux  = -Wl,-z,defs
LDFLAGS      = $(LDFLAGS_$(PLATFORM)) -L. $(shell $(PYTHON_CONFIG) --ldflags --embed) $(patsubst %,-L%,$(LIBRARY_DIRS)) -Wl,--as-needed

CXXFLAGS     = -D_GNU_SOURCE -D_DARWIN_C_SOURCE -DWITHOUT_CMS_FRAMEWORK=1 -D__STDC_LIMIT_MACROS \
               -D__STDC_FORMAT_MACROS -U__DEPRECATED -fPIC -g -O2 -W -Wall -Wno-long-long \
               -pedantic -std=c++14 -Wno-unused-local-typedefs -I$(SRCDIR) $(patsubst %,-I%,$(INCLUDE_DIRS)) \
               $(shell $(PYTHON_CONFIG) --cflags --includes --embed)
ROOTC_LIBS   = -L/usr/lib64/root -lCore -lImt -lRIO -lNet -lHist -lROOTVecOps -lTree \
                -lRint -lMatrix -lMathCore -lThread -lMultiProc \
                -lROOTDataFrame -pthread -lm -ldl -rdynamic
ROOTG_LIBS   = $(ROOTC_LIBS) -lTreePlayer -lGpad -lGraf3d -lGraf \
               -lPhysics -lPostscript -lASImage -ljpeg -lpng
OTHER_LIBS_Darwin =
OTHER_LIBS_Linux  = -lrt
OTHER_LIBS   = -lclasslib -lpcre -lz -lpthread -lprotobuf -ldl $(OTHER_LIBS_$(PLATFORM))
PYTHON_LIBS  = -lboost_python $(shell $(PYTHON_CONFIG) --libs  --embed)


LIB_SRC      = DQM/DQMRenderPlugin.cc \
               DQM/VisDQMBuf.cc \
               DQM/VisDQMCache.cc \
               DQM/VisDQMError.cc \
               DQM/VisDQMFile.cc \
               DQM/VisDQMIndex.cc
LIB_OBJ      = $(patsubst %.cc,%.o,$(notdir $(LIB_SRC)))
LIB_LINK     = $(CXX) $(CXXFLAGS) -shared -o $@ $(LIB_OBJ) \
               $(LDFLAGS) $(OTHER_LIBS)

COLL_SRC     = DQM/DQMCollector.cc # DQM/DQMNet.cc DQM/DQMError.cc
COLL_OBJ     = $(patsubst %.cc,%.o,$(notdir $(COLL_SRC)))
COLL_LINK    = $(CXX) $(CXXFLAGS) -fPIE -o $@ $(COLL_OBJ) \
               $(LDFLAGS) $(OTHER_LIBS)

EXT_SRC      = DQM/serverext.cc DQM/DQMNet.cc DQM/DQMError.cc
EXT_OBJ      = $(patsubst %.cc,%.o,$(notdir $(EXT_SRC)))
EXT_LINK     = $(CXX) $(CXXFLAGS) -shared -o $@ $(EXT_OBJ) \
               $(LDFLAGS) -lDQMGUI $(OTHER_LIBS) $(PYTHON_LIBS) -lpng

INDEX_SRC    = DQM/index.cc DQM/DQMNet.cc DQM/DQMError.cc \
               DQM/DQMStore.cc DQM/MonitorElement.cc DQM/ROOTFilePB.pb.cc \
               DQM/QTest.cc DQM/QReport.cc \
               DQM/StreamSample.pb.cc
INDEX_OBJ    = $(patsubst %.cc,%.o,$(notdir $(INDEX_SRC)))
INDEX_LINK   = $(CXX) $(CXXFLAGS) -fPIE -o $@ $(INDEX_OBJ) \
               $(LDFLAGS) -lDQMGUI $(ROOTC_LIBS) $(OTHER_LIBS)

RENDER_SRC   = DQM/render.cc DQM/DQMNet.cc DQM/DQMError.cc
RENDER_OBJ   = $(patsubst %.cc,%.o,$(notdir $(RENDER_SRC)))
RENDER_LINK  = $(CXX) $(CXXFLAGS) -fPIE -o $@ $(RENDER_OBJ) \
               $(LDFLAGS) -lDQMGUI $(ROOTG_LIBS) $(OTHER_LIBS) -ljpeg

vpath %.cc $(SRCDIR)/DQM $(MONITOR_ROOT)/xinclude/DQM $(MONITOR_ROOT)/include/DQM
vpath %.proto $(SRCDIR)/ $(MONITOR_ROOT)/xinclude/ $(MONITOR_ROOT)/include
all: visDQMIndex visDQMRender DQMCollector Accelerator.so libDQMGUI.so
clean:; rm -f *.o *.so visDQMIndex visDQMRender
%.o: %.cc; $(CXX) $(CXXFLAGS) -c $< -o $@
DQM/StreamSample.pb.cc: DQM/StreamSample.proto
	protoc --cpp_out=. DQM/StreamSample.proto
StreamSample.pb.o: DQM/StreamSample.pb.cc
	$(CXX) $(CXXFLAGS) -c $< -o $@
index.o: DQM/index.cc DQM/StreamSample.pb.cc
	$(CXX) $(CXXFLAGS) -c $< -o $@
render.o: DQM/render.cc DQM/VisDQMRenderTools.h DQM/VisDQMTools.h DQM/VisDQMIndex.h DQM/Objects.h DQM/DQMRenderPlugin.h
	$(CXX) $(CXXFLAGS) -c $< -o $@
libDQMGUI.so: $(LIB_OBJ); $(LIB_LINK)
Accelerator.so: $(EXT_OBJ) libDQMGUI.so; $(EXT_LINK)
DQMCollector: $(COLL_OBJ); $(COLL_LINK)
visDQMIndex: $(INDEX_OBJ) DQM/VisDQMTools.h libDQMGUI.so; $(INDEX_LINK)
visDQMRender: $(RENDER_OBJ) libDQMGUI.so; $(RENDER_LINK)
ifeq ($(strip $(MONITOR_ROOT)),)
DQM/ROOTFilePB.pb.cc: DQM/ROOTFilePB.proto; protoc --cpp_out=. $<
else
DQM/ROOTFilePB.pb.cc: DQM/ROOTFilePB.proto; protoc --cpp_out=. $< -I$(MONITOR_ROOT)/xinclude/ -I$(MONITOR_ROOT)/include/
endif
ROOTFilePB.pb.o: DQM/ROOTFilePB.pb.cc; $(CXX) $(CXXFLAGS) -c $< -o $@
