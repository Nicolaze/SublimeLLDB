"""
LLDB AppKit formatters

part of The LLVM Compiler Infrastructure
This file is distributed under the University of Illinois Open Source
License. See LICENSE.TXT for details.
"""
# summary provider for NSData
import lldb
import ctypes
import objc_runtime
import metrics

statistics = metrics.Metrics()
statistics.add_metric('invalid_isa')
statistics.add_metric('invalid_pointer')
statistics.add_metric('unknown_class')
statistics.add_metric('code_notrun')

# despite the similary to synthetic children providers, these classes are not
# trying to provide anything but the port number of an NSMachPort, so they need not
# obey the interface specification for synthetic children providers
class NSMachPortKnown_SummaryProvider:
	def adjust_for_architecture(self):
		pass

	def __init__(self, valobj, params):
		self.valobj = valobj;
		self.sys_params = params
		if not(self.sys_params.types_cache.NSUInteger):
			if self.sys_params.is_64_bit:
				self.sys_params.types_cache.NSUInteger = self.valobj.GetType().GetBasicType(lldb.eBasicTypeUnsignedLong)
			else:
				self.sys_params.types_cache.NSUInteger = self.valobj.GetType().GetBasicType(lldb.eBasicTypeUnsignedInt)
		self.update();

	def update(self):
		self.adjust_for_architecture();

	# one pointer is the ISA
	# then we have one other internal pointer, plus
	# 4 bytes worth of flags. hence, these values
	def offset(self):
		if self.sys_params.is_64_bit:
			return 20
		else:
			return 12

	def port(self):
		vport = self.valobj.CreateChildAtOffset("port",
							self.offset(),
							self.sys_params.types_cache.NSUInteger)
		return vport.GetValueAsUnsigned(0)


class NSMachPortUnknown_SummaryProvider:
	def adjust_for_architecture(self):
		pass

	def __init__(self, valobj, params):
		self.valobj = valobj;
		self.sys_params = params
		self.update();

	def update(self):
		self.adjust_for_architecture();

	def port(self):
		stream = lldb.SBStream()
		self.valobj.GetExpressionPath(stream)
		num_children_vo = self.valobj.CreateValueFromExpression("port","(int)[" + stream.GetData() + " machPort]")
		if num_children_vo.IsValid():
			return num_children_vo.GetValueAsUnsigned(0)
		return '<variable is not NSMachPort>'


def GetSummary_Impl(valobj):
	global statistics
	class_data,wrapper = objc_runtime.Utilities.prepare_class_detection(valobj,statistics)
	if wrapper:
		return wrapper
	
	name_string = class_data.class_name()
	if name_string == 'NSMachPort':
		wrapper = NSMachPortKnown_SummaryProvider(valobj, class_data.sys_params)
		statistics.metric_hit('code_notrun',valobj)
	else:
		wrapper = NSMachPortUnknown_SummaryProvider(valobj, class_data.sys_params)
		statistics.metric_hit('unknown_class',str(valobj) + " seen as " + name_string)
	return wrapper;

def NSMachPort_SummaryProvider (valobj,dict):
	provider = GetSummary_Impl(valobj);
	if provider != None:
		if isinstance(provider,objc_runtime.SpecialSituation_Description):
			return provider.message()
		try:
			summary = provider.port();
		except:
			summary = None
		if summary == None:
			summary = '<variable is not NSMachPort>'
		if isinstance(summary, basestring):
			return summay
		return 'mach port: ' + str(summary)
	return 'Summary Unavailable'

def __lldb_init_module(debugger,dict):
	debugger.HandleCommand("type summary add -F NSMachPort.NSMachPort_SummaryProvider NSMachPort")