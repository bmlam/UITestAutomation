#!/usr/bin/python

"""
A python rewrite of Jonathan Penn's screenshooter for test automation
Task perform by this script:
	* xcodebuild the app bundle
	* Determine the simulatedDevice
	* Fire up instruments to deploy the build app bundle to the targeted Simulator, passing along the UI automation script
	* instruments plays the automation script which also takes screen shots as .png files saved in the location given by "-e UIARESULTSPATH". However instruments seems to remember the run number and always create a new subfolder per run.
	* Copy the png files from the given location to a more "persistent" location, creating a folder whose name includes the the device type, locale and language

"""

import argparse 
import glob 
import inspect 
import os 
import re
import shutil
import subprocess 
import sys 
import time 

g_screenshotsBakRoot=  os.path.join( os.environ[ 'HOME' ] , 'Desktop',  'TestAuto_screenshots' )
g_bundleDir			= "" # set later
g_traceResultsDir	= "" # set later

g_uiPlaybook= "uiPlayBook.js"

g_cntDisplayed = 0

def _dbx ( text ):
    sys.stdout.write( '  Debug(%s - Ln %d): %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 

def _infoTs ( text, withTS = False ):
	if withTS:
		print( '%s (Ln %d) %s' % ( time.strftime("%H:%M:%S"), inspect.stack()[1][2], text ) )
	else :
		print( 'INFO (Ln %d) %s' % ( inspect.stack()[1][2], text ) )

def _errorExit ( text ):
    sys.stderr.write( 'ERROR raised from %s - Ln %d: %s\n' % ( inspect.stack()[1][3], inspect.stack()[1][2], text ) ) 
    sys.exit(1)

def parseCmdLine() :
	buildOutputLoc	= os.path.join( "/tmp", "TestAutomat" )

	parser = argparse.ArgumentParser()
	# lowercase shortkeys

	parser.add_argument( '-o', '--build_output', help='build output location', default= buildOutputLoc )
	parser.add_argument( '-p', '--project_dir', help='Top level directory where xcode project file resides', default = '..' )
	parser.add_argument( '-s', '--screenshots_root', help='root location for screenshots. A subfolder with the ui_script name will be created', default=g_screenshotsBakRoot )
	parser.add_argument( '-u', '--ui_script', help='build output location', default=g_uiPlaybook )

	cleanSwithGroup = parser.add_mutually_exclusive_group(required=False)
	cleanSwithGroup.add_argument('-C', '--clean', dest='cleanSwitch', action='store_true')
	cleanSwithGroup.add_argument('-c', '--no-clean', dest='cleanSwitch', action='store_false')
	parser.set_defaults(cleanSwitch=True)

	result= parser.parse_args()

	global g_bundleDir
	g_bundleDir			= "%s/app.app" %  buildOutputLoc
	global g_traceResultsDir
	g_traceResultsDir	= os.path.join( buildOutputLoc, 'traces' )

	for (k, v) in vars( result ).iteritems () : _dbx( "%s : %s" % (k, v) )

	return result

def assertUIPlayBook ( path ):
	if not os.path.isfile( path ):
		_errorExit( "Playbook '%s' not found or accessible" % path )
	_infoTs( "Ok, will use '%s' as UI script." % path )

def getListOfLangsAndDevicesFromFile(filePath):
	"""Decompose the file content into list of languages and device types 
	"""

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

def performBuild ( projectDir, buildOutputDir, doClean = True ):
	""" A wrapper around `xcodebuild` that tells it to build the app in the temp
	directory. If your app uses workspaces or special schemes, you'll need to
	specify them here.
	
	Use `man xcodebuild` for more information on how to build your project.
	"""

	xcworkspaceFiles = glob.glob( '%s/*.xcworkspace' % projectDir )
	if len( xcworkspaceFiles ) > 0 :
		_errorExit ( "Found at least one xcworkspace files in '%s'. Building with xcworkspace is not yet supported!" % projectDir )

	cmdArgs = [ 'xcodebuild'
		, '-sdk', 'iphonesimulator'
		, 'CONFIGURATION_BUILD_DIR=' + buildOutputDir
		, 'PRODUCT_NAME=' + 'app'
		]

	
	if doClean: 
		_infoTs( "Building with __clean__ ..." , True )
		cmdArgs.append( 'clean' )
	else :
		_infoTs( "Building without __clean__ ..."  )
	cmdArgs.append( 'build' )

	savedDir = os.getcwd()
	os.chdir( projectDir )
	subprocess.check_call ( cmdArgs )
	os.chdir( savedDir )

def mkdir ( path ):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
		raise
 
def rmdirAskConditionally( path, dirUsage ):
	if os.path.isdir( path ):
		if not path.startswith( '/tmp/' ):
			answer = raw_input( "Non-temp directory '%s' used for %s already exists. Enter 'yes' to proceed for removal or anything else to abort: " % path, dirUsage )
			if answer == 'yes':
				None # back to common path
			else:
				_errorExit( "Script aborted to retain directory '%s' " % path )

		shutil.rmtree( path )
	else:
		_dbx( "'%s' does not exist" % path )

def assertScreenshotsBackupRoot ( path ):
	if os.path.isdir( path ):
		answer = raw_input( "Directory '%s' already exists. Enter 'yes' to proceed for removal or anything else to abort: " % path )
		if answer == 'yes':
			shutil.rmtree( path )
		else:
			_errorExit( 'Script aborted.')
			
	mkdir( path )

def recreateTraceOutputDir ( path ):
	"""
    Removes the trace results directory. We need to do this because Instruments
    keeps appending new trace runs and it's simpler for us to always assume
    there's just one run recorded where we look for screenshots.
	"""
	# _dbx( path )
	rmdirAskConditionally( path , 'traceOutput' )
	mkdir( path )

def startSimulatorAndPlayUIScript( lang, dev, ui_script, bundleDir, instrumOutputLoc ):
	_infoTs( "Running script for %s on %s ..." % ( lang, dev ) , True )
	global g_cntDisplayed

	if False :
		cmdGetDir = 'xcode-select -print-path' 
		proc = subprocess.popen ( cmdGetDir , stdout= subprocess.PIPE )
		devToolsDir = proc.stdout.read()
		if None == devToolsDir:
			_errorExit( "'%s' failed!" % cmdGetDir )

	traceTemplate = 'Automation'
	cmdArgsInstrum = [ './unix_instruments.sh'
		, '-w', dev
		, '-D', os.path.join( instrumOutputLoc, 'trace' )
		, '-t', traceTemplate 
		, bundleDir
		, '-e', 'UIARESULTSPATH', instrumOutputLoc
		, '-e', 'UIASCRIPT', ui_script
		# , '-AppleLanguages', lang
		# , '-AppleLocale', lang 
	]
	g_cntDisplayed += 1
	if g_cntDisplayed % 7 == 1: _dbx( "Command to be submitted:\n" + ' '.join( cmdArgsInstrum ) + '\n' )

	os.environ[ 'UIA_LANGUAGE' ] = lang
		
	subprocess.check_call( cmdArgsInstrum )


def backupScreenshots( srcRoot, tgtRoot, lang, dev ):
	"""
    Since we always clear out the trace results before every run, we can
    assume that any screenshots were saved in the "Run 1" directory. Copy them
    to the screenshotsBackupLoc's language folder!
	"""
	tgtDir = os.path.join( tgtRoot, makeExpandFriendlyPath( dev ), lang )
	mkdir( tgtDir )

	cntFiles = 0
	cntRotated = 0
	srcDir = os.path.join( srcRoot, 'Run 1' )
	_dbx( "Copying png files from '%s' to '%s' ..." % ( srcDir, tgtDir ) )
	for file in glob.glob( srcDir + '/*.png' ):
		if file.find( 'landscape' ) >= 0 :
			subprocess.check_call( [ 'sips', '-r', '-90', file ] )
			cntRotated += 1
		shutil.copy( file, tgtDir )
		cntFiles += 1
	_dbx( "Files rotated: %d, copied: '%d'" % ( cntRotated, cntFiles ) )

def closeSimulator() :
	"""
	I know, I know. It says "iPhone Simulator". For some reason,
    that's the only way Applescript can identify it.
	"""
	cmdArgs = ['osascript', '-e', 'tell application "iPhone Simulator" to quit' ]
	# subprocess.check_call( cmdArgs )
	time.sleep( 1 )

def makeExpandFriendlyPath( string ):
	# replace round brackets characters and space with underscore
	return re.sub(  '[\(\) ]', '_', string )

def main():
	scriptBasename = os.path.basename( __file__ )
	argObject = parseCmdLine()

	assertUIPlayBook( argObject.ui_script )
	uiScriptBaseNameNoSuffix = os.path.splitext( os.path.basename( argObject.ui_script ) )[ 0 ]
	screenshotsBakDir = os.path.join( argObject.screenshots_root ,  uiScriptBaseNameNoSuffix )

	# we check dir backup directory at this early stage so not too time is wasted when user does
	# want to keep the content of the target directory
	assertScreenshotsBackupRoot ( screenshotsBakDir )
	_infoTs( "Screenshots will be backed to '%s'" % screenshotsBakDir )

	devs, langs = getListOfLangsAndDevicesFromFile ( './listOfLangsAndDevices.txt' )
	_infoTs( 'Will iterate over these lang(s) : \t%s' % '; '.join( langs ) )
	_infoTs( 'Will iterate over these dev(s) : \t%s'  % '; '.join( devs ) )

	performBuild( argObject.project_dir, argObject.build_output, argObject.cleanSwitch )

	for dev in devs:
		for lang in langs:
			recreateTraceOutputDir( g_traceResultsDir )

			# instruments will create trace.trace under traceOutputLoc on each run
			traceTraceDir = os.path.join( argObject.build_output, 'trace.trace' )  
			if os.path.isdir( traceTraceDir ): shutil.rmtree( traceTraceDir )

			# instruments creates "Run 1", "Run1 (2)", "Run1 (3)" etc under the given location
			run1Dir = os.path.join( argObject.build_output, 'Run 1' )  
			if os.path.isdir( run1Dir ): shutil.rmtree( run1Dir )

			startSimulatorAndPlayUIScript( lang= lang, dev= dev, ui_script= argObject.ui_script , bundleDir= g_bundleDir, instrumOutputLoc= argObject.build_output )
			backupScreenshots( argObject.build_output, screenshotsBakDir, lang, dev )

			_infoTs( "Closing simulator %s" % dev )
			closeSimulator()

	_infoTs( "\n\n%s completed normally." % scriptBasename , True )
			
main()

