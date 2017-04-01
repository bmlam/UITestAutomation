#!/usr/bin/python

"""
Remove a given app from the simulators specified by a config file
In the long term, this script should be integrated into the main UI test automation tool
"""

import calendar 
import argparse 
import glob 
import inspect 
import os 
# import re
# import shutil
import subprocess 
import sys 
# import tempfile 
import time 

#
#MARK: Show script execution breadcrumbs
#

def _dbx ( text ):
    sys.stdout.write( '  Debug(%s - Ln %d): %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 

def _infoTs ( text, withTS = False ):
	if withTS:
		print( '\n%s (Ln %d) %s' % ( time.strftime("%H:%M:%S"), inspect.stack()[1][2], text ) )
	else :
		print( '\nINFO (Ln %d) %s' % ( inspect.stack()[1][2], text ) )

def _errorExit ( text ):
    sys.stderr.write( '\nERROR raised from %s - Ln %d: %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 
    sys.exit(1)

#
#MARK: Command line interface
#
def parseCmdLine() :

	parser = argparse.ArgumentParser()
	# lowercase shortkeys

	parser.add_argument( '-a', '--appFullName', help='For example com.sefrowo.www.TestApp', required= True )
	# long argument names from here
	parser.add_argument( '--langDevFile', help='full path of the file listing languages and devices to test', required= True )

	result= parser.parse_args()

	# for (k, v) in vars( result ).iteritems () : _dbx( "%s : %s" % (k, v) )

	# derive settings

	return result

#
#MARK: Handling subprocess stdout and stderr
#

def handleConsoleOutput ( text, isStderr, showLines, abortOnError= False ):
	if isStderr: type = 'stderr' 
	else: type = 'stdout'
	callerLine = inspect.stack()[1][2]
	callerName = inspect.stack()[1][3]

	lines = text.split( "\n" )
	realLineCnt = 0
	for line in lines:
		if line.strip() != line: realLineCnt += 1
	if  realLineCnt > 0 :
		sys.stdout.write( "** ShortenedConsoleOutput: last %d (of %d) %s lines from caller %s at Line %d: \n%s" % 
			( showLines, len( lines ), type, callerName, callerLine, lines[ -showLines: ] ) ) 
		if isStderr:
			path = os.path.join( g_errlogDir, 'ErrorFrom_%s_Ln%d.log' % ( callerName, callerLine ) )
			fileTextAndLog2Console( text= text, consoleMsgPrefix= "Error output automatically saved to", outPath= path )
			if abortOnError:
				_errorExit( "Aborted since error is flagged as error" ) 

	else:
		sys.stdout.write( "** ShortenedConsoleOutput: %s from caller %s at Line %d is empty!\n" % ( type, callerName, callerLine ) )

def fileTextAndLog2Console( text, consoleMsgPrefix, outPath= None ):
	if outPath == None:
		outPath = tempfile.mktemp()
	outF = open( outPath, "w" )
	_infoTs( "%s '%s'" % ( consoleMsgPrefix, outPath ) )
	outF.write( text )
	outF.close( )

#
#MARK: dealing with Simulators
#
def closeSimulatorApp():
	"""
	"""
	cmdArgs = [ 'osascript'
		, '-e', 'tell app "Simulator" to quit'
		]
	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	outLines = stdOutput.split( "\n" )
	if outLines > 0: _infoTs( "Last lines of stdout:\n%s\n" % ( '\n'.join( outLines[ -3: ] ) ) )

	if len( errOutput ) > 0 :
		errLines = errOutput.split( "\n" )
		_infoTs( "Last lines of stdout:\n%s\n" % ( '\n'.join( outLines[ -3: ] ) ) )
		fileTextAndLog2Console( text= errOutput, consoleMsgPrefix= "Stderr saved to", outPath= None )

def bootDevice( dev ):
	"""
	"""
	cmdArgs = [ 'xcrun', 'simctl' 
		, 'boot', dev
		]
	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 2 )
	if len( errOutput ) > 0 :
		handleConsoleOutput ( text= errOutput, isStderr= True, showLines= 10 ) 

def shutdownDevice( dev ):
	"""
	"""
	cmdArgs = [ 'xcrun', 'simctl' 
		, 'shutdown', dev
		]
	# _dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 2 )

	if len( errOutput ) > 0 :
		handleConsoleOutput ( text= stdOutput, isStderr= True, showLines= 4 )
		fileTextAndLog2Console( text= errOutput, consoleMsgPrefix= "shutdownDevice stderr saved to", outPath= None )

def removeAppFromDevice( dev, appId ):
	"""
	"""
	cmdArgs = [ 'xcrun', 'simctl' , 'uninstall', dev, appId ]
	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 2 )

	if len( errOutput ) > 0 :
		handleConsoleOutput ( text= stdOutput, isStderr= True, showLines= 4 )
		fileTextAndLog2Console( text= errOutput, consoleMsgPrefix= "shutdownDevice stderr saved to", outPath= None )

#
#MARK: Other helpers
#
def getListOfLangsAndDevicesFromFile(filePath):
	"""Decompose the file content into list of languages and device types 
	"""
	_infoTs( "Reading languages and devices to test from %s" % filePath )

	fieldSep = ':'
	langLiteral = 'lang'
	devLiteral  = 'dev'

	try :
		fh= open( filePath, 'r')
	except IOError:
		_errorExit( 'Could not read file %s' % filePath )

	langs= []
	devs= []

	lineNo= 0
	for lineIn in fh.readlines():
		lineNo+= 1
		line =lineIn.strip()
		if not line.startswith("#"):
			if len( line ) > 0:
				fields = line .split ( fieldSep )
				# _dbx( len( fields ) )
				if len ( fields ) != 2:

					_errorExit( "Each payload line in '%s' is must contain 2 fields separated by '%s'. Line %d is invalid" % ( filePath, fieldSep, lineNo) )

				key, value = fields[0:2] # start from 0 and take 2
				if key == devLiteral :
					if value in devs :
						_errorExit( "Device %s found again in line %d. Dupes are not permitted!" % (value, lineNo) )
					devs.append( value )
				elif key == langLiteral :
					if value in langs :
						_errorExit( "Device %s found again in line %d. Dupes are not permitted!" % (value, lineNo) )
					langs.append( value )
				else:
					_errorExit( "The keyword found in line %d of '%s' is invalid" % ( lineNo, filePath ) )

	return devs, langs

def main():

	startTime= time.strftime("%H:%M:%S")
	scriptBasename = os.path.basename( __file__ )

	argObject = parseCmdLine()

	devs, langs = getListOfLangsAndDevicesFromFile ( argObject.langDevFile )
	_infoTs( 'Will iterate over these dev(s) : \t%s'  % '__ ; __'.join( devs ) )

	if True:
		closeSimulatorApp()

	for dev in devs:
		bootDevice( dev ) # should not matter if device is already up
		removeAppFromDevice( dev, argObject.appFullName )
		shutdownDevice( dev ) # should reduce system load
		_infoTs( "Done with simulator %s" % ( dev ) )

	_infoTs( "\n%s completed normally. StartTime was %s" % ( scriptBasename, startTime) , True )
	
main()
