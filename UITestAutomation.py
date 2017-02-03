#!/usr/bin/python

"""
Originally based on Jonathan Penn's screenshooter for test automation and adopted 
to work with Apple's test automation framework. Also courtesy some third party tools
prominenty by zmeyc to make screenshots and delaying work

Tasks performed by this script ( _IDEALLY_ ):
	* xcodebuild the app bundle
	* Determine the simulatedDevice
	* Fire up instruments to deploy the build app bundle to the targeted Simulator, passing along the UI automation script
	* instruments plays the automation script which also takes screen shots as .png files saved in the location given by "-e UIARESULTSPATH". However instruments seems to remember the run number and always create a new subfolder per run.
	* Copy the png files from the given location to a more "persistent" location, creating a folder whose name includes the the device type, locale and language

In practice in my test and trial approach the current sequence is chosen sicne it SHOULD work:
	* xcodebuild the app bundle
	* iterate over target dvices
	* 	iterate over target languages
	* 		xcrun to install the app to the target dvice with the target app
	* 		xcodebuild to fire the UI test target (which exercise the test cases and make screenshots )
	* 		save the taken screenshots to the appropiate subdirectory based on device and language

Some coding convention to bear in mind:
	assignment: always leave space to both side of = to be consistent with swift. Named argument in method calls may be exception

	useful commands:
		xcrun instruments -s devices # show available devices
		xcrun simctl boot <device>   # boots a device but we do not see the Simulator popping up! Just internal state set to booted
		xcrun simctl install <device> <app bundle path>  # installs the app but does not seem to open an Simulator app
		xcrun simctl launch <device> <app name in reverse URL notation>  # prints the pid of the app process on Mac but no Simulator GUI!
		xcrun simctl list # list all simulator somehow existing, but also status of valid devices!

	One way to bring up the Simulator GUI of the targeted device is Simulator -> Hardware -> <choose dvice>. Doing so may return the error message: "device already booted" so we need to "simctl shutdown <device>" first.
	So if "simctl launch" is decoupled from the Simulator GUI, does it mean we could test devices in parallel?

"""

import calendar 
import argparse 
import glob 
import inspect 
import os 
import re
import shutil
import subprocess 
import sys 
import tempfile 
import time 

g_screenshotsBakRoot=  os.path.join( os.environ[ 'HOME' ] , 'Desktop',  'TestAuto_screenshots' )
g_buildTestOutputDefaultRoot	= os.path.join( "/tmp", "UITestAutomatationOutput" )
g_userHome= os.path.expanduser( '~' )
g_errlogDir	= os.path.join( g_userHome, "UITestAutomatation_ErrorLogs" )

g_cntDisplayed = 0

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
		sys.stdout.write( "** ShortenedConsoleOutput: %s from caller %s at Line %d is empty!\n\n" % ( type, callerName, callerLine ) )

def parseCmdLine() :

	parser = argparse.ArgumentParser()
	# lowercase shortkeys

	parser.add_argument( '-a', '--appName', help='normally this is the prefix of the main ".xcodeproj" file', required= True )
	parser.add_argument( '-o', '--buildTestOutputDir'
		, help='build and test output location for xcodebuild. Will default to "%s" + AppName supplied' % g_buildTestOutputDefaultRoot	
		)
	parser.add_argument( '-p', '--projectRoot', help='Top level directory where xcode project file resides', default = '..' )
	parser.add_argument( '-s', '--screenshotsArchiveRoot'
		, help='root location for screenshots. Subfolders based on appName, device and lang will be created', default=g_screenshotsBakRoot )

	cleanSwithGroup = parser.add_mutually_exclusive_group(required=False)
	cleanSwithGroup.add_argument('-C', '--clean', dest='cleanSwitch', action='store_true')
	cleanSwithGroup.add_argument('-c', '--no-clean', dest='cleanSwitch', action='store_false')
	parser.set_defaults(cleanSwitch= False)

	result= parser.parse_args()

	for (k, v) in vars( result ).iteritems () : _dbx( "%s : %s" % (k, v) )

	# derive settings
	if result.buildTestOutputDir == None:  result.buildTestOutputDir = os.path.join( g_buildTestOutputDefaultRoot, result.appName )
	return result

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

def performBuild ( appName, projectDir, buildOutputDir, doClean = False ):
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
		, '-scheme', appName
		, 'CONFIGURATION_BUILD_DIR=' + buildOutputDir
		# , 'PRODUCT_NAME=' + 'app'
		]

	bundlePath = os.path.join( buildOutputDir, appName + '.app' )
	
	if doClean: 
		_infoTs( "Building with __clean__ ..." , True )
		cmdArgs.append( 'clean' )
	else :
		_infoTs( "Building without __clean__ ..."  )
	cmdArgs.append( 'build' )

	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	savedDir = os.getcwd()
	os.chdir( projectDir )
	# subprocess.check_call ( cmdArgs )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	outLines = stdOutput.split( "\n" )
	_infoTs( "Last lines of stdout:\n%s\n" % ( '\n'.join( outLines[ -5: ] ) ) )

	buildStdoutPath = tempfile.mktemp()
	outF = open( buildStdoutPath, "w" )
	_infoTs( "***************** Piping xcodebuild stdout to '%s' " % buildStdoutPath )
	outF.write( stdOutput )
	outF.close( )

	bundleModTimeSecs = fileModTimeAs( path= bundlePath, format= 'SecondsSinceEpoch' )
	currentSecs = calendar.timegm( time.gmtime() )
	secsDelta = currentSecs - bundleModTimeSecs 
	_infoTs( "Bundle '%s' built at %f and now is %f. Delta is %d" % ( bundlePath, bundleModTimeSecs, currentSecs, secsDelta ) ) 
	secsTolerance = 3

	if len( errOutput ) > 0 :
		errLines = errOutput.split( "\n" )
		_dbx( "lines in stderr: %d" % len( errLines ) )
		_infoTs( "Last lines of stderr:\n%s\n" % ( '\n'.join( errLines[ -10: ] ) ) )

		buildStderrPath = tempfile.mktemp()
		errF = open( buildStderrPath, "w" )
		_infoTs( "****************** Piping xcodebuild stderr to '%s'" % ( buildStderrPath ) )
		errF.write( errOutput )
		errF.close( )

		if secsDelta < secsTolerance : 
			_infoTs( "We continue since delta in seconds is less than %d" % secsTolerance )
		else:
			if True: 
				_infoTs( "Ignoring error from xcodebuild during script development/test!!!" )
			else: 
				answer = raw_input( "Continue processing? Enter 'yes' to proceed or anything else to abort: " )
				if answer == 'yes':
					None # back to common path
				else:
					_errorExit( "Script aborted on request" )


	os.chdir( savedDir )

	return bundlePath

def mkdir ( path ):
	if os.path.isdir( path ):
		return
	else:
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

def assertScreenshotsBackupDir ( path ):
	if os.path.isdir( path ):
		nodesInDir = os.listdir( path )
		_infoTs( "Directory '%s' for backup of screenshots already exists. Checking it content.." % path )
		if len( nodesInDir ) == 0:
			_infoTs( "Ok, directory is empty. Processing will continue" )
			return
		else:
			_infoTs( "The directory has %d nodes. Examples: %s" % ( len( nodesInDir ), ';'.join( nodesInDir[0:3] ) ) )
			answer = raw_input( "Enter 'yes' to proceed for removal or anything else to abort: " )
			if answer == 'yes':
				shutil.rmtree( path )
			else:
				_errorExit( 'Script aborted.')
			
	mkdir( path )

def backupScreenshots( srcRoot, tgtDir ):
	"""
	"""

	cntFiles = 0
	cntRotated = 0
	srcDir = srcRoot
	_dbx( "Copying png files from '%s' to '%s' ..." % ( srcDir, tgtDir ) )
	for file in glob.glob( srcDir + '/*.png' ):
		if file.find( 'landscape' ) >= 0 :
			subprocess.check_call( [ 'sips', '-r', '-90', file ] )
			cntRotated += 1
		shutil.copy( file, tgtDir )
		cntFiles += 1
	_dbx( "Files rotated: %d, copied: '%d'" % ( cntRotated, cntFiles ) )

def makeExpandFriendlyPath( string ):
	# replace round brackets characters and space with underscore
	return re.sub(  '[\(\) ]', '_', string )

def fileModTimeAs ( path, format ): 
	"""return modification time as in desired format
	"""
	if not os.path.exists( path ):
		_errorExit( "Node %s does not exists" % path )

	gmtime = os.path.getmtime( path )
	if format == 'SecondsSinceEpoch': # consider string constants for formats!
		return gmtime
	elif format == 'Components':
		_errorExit( "Format %s is not _yet_ supported" % format )
	else:
		_errorExit( "Format %s is not supported" % format )

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
	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 2 )

	if len( errOutput ) > 0 :
		handleConsoleOutput ( text= stdOutput, isStderr= True, showLines= 4 )
		fileTextAndLog2Console( text= errOutput, consoleMsgPrefix= "shutdownDevice stderr saved to", outPath= None )

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

def deployAppToDeviceAndSetLang( lang, dev, bundlePath ):
	"""
	Since we do not know another way to change the language setting of the Simulator, the next best
	approach seems to be setting the language for the app, and this seems to be possible only while we
	are deploying it
	"""
	shutdownDevice( dev ) # shutdown the device first to get a defined state!
	bootDevice( dev ) 
	cmdArgs = [ 'xcrun', 'simctl' 
		, 'install', dev, bundlePath 
		, '-AppleLanguages', lang
		]
	_dbx( "Running: %s" % " ".join( cmdArgs ) )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 3 )
	if len( errOutput ) > 0 :
		errLines = errOutput.split( "\n" )
		_infoTs( "lines in stderr: %d" % len( errLines ) )

		_errorExit( "Last lines of stderr:\n%s\n" % ( '\n'.join( errLines[ -10: ] ) ) )

def fileTextAndLog2Console( text, consoleMsgPrefix, outPath= None ):
	if outPath == None:
		outPath = tempfile.mktemp()
	outF = open( outPath, "w" )
	_infoTs( "%s '%s'" % ( consoleMsgPrefix, outPath ) )
	outF.write( text )
	outF.close( )

def startUITestTarget( projectDir, lang, dev, outputDir, appName ):
	"""
	Sofar I only know how to call xcodebuild to build the app and test target and run the test target.
	I have seen that the language set for the app previously using "xcrun " does get persisted in the Simulator.
	It is indeed stupid to build again but until I know a more efficient way, I have to put up with
	this monkey solution.
	"""

	savedDir = os.getcwd(); os.chdir( projectDir )

	shutdownDevice( dev ) # since xcodebuild complained about dev in booted state
	cmdArgs = [ 'xcodebuild', 'test' 
				,'-target',  appName + 'Tests'
	   			,'-derivedDataPath', outputDir
				,'-scheme',  appName 
           		,'-sdk', 'iphonesimulator' 
           		,'-destination', 'platform=iOS Simulator,OS=10.2,name=%s' % dev
		]
	_infoTs( "Running: %s" % " ".join( cmdArgs ), True )

	proc= subprocess.Popen( cmdArgs ,stdin=subprocess.PIPE ,stdout=subprocess.PIPE ,stderr=subprocess.PIPE)
	stdOutput, errOutput= proc.communicate( )

	handleConsoleOutput ( text= stdOutput, isStderr= False, showLines= 20 )

	if len( errOutput ) > 0:
		handleConsoleOutput ( text= errOutput, isStderr= False, showLines= 10, abortOnError= True ) # fixme: test abortOnError

		devPretty= makeExpandFriendlyPath( dev )
		langPretty= makeExpandFriendlyPath( lang )
		outPath= os.path.join( outputDir, "UITest_StdERR__%s_%s" % ( devPretty, langPretty ) )
		fileTextAndLog2Console( text= errOutput, consoleMsgPrefix= "Stderr of xcodebuild saved to", outPath= outPath )

		answer = raw_input( "Continue processing? Enter 'yes' to proceed or anything else to abort: " )
		if answer == 'yes':
			None # back to common path
		else:
			_errorExit( "Script aborted on request" )

	os.chdir( savedDir )

def setup():
	mkdir( g_errlogDir )	

def main():
	scriptBasename = os.path.basename( __file__ )
	argObject = parseCmdLine()

	setup()

	_infoTs( "Build and test output dir will be '%s'" % argObject.buildTestOutputDir )
	screenshotsArchiveRoot = argObject.screenshotsArchiveRoot 

	_infoTs( "Screenshots for all device and lang pairing will be backed up to '%s'" % screenshotsArchiveRoot )

	devs, langs = getListOfLangsAndDevicesFromFile ( './listOfLangsAndDevices.txt' )
	_infoTs( 'Will iterate over these lang(s) : \t%s' % '; '.join( langs ) )
	_infoTs( 'Will iterate over these dev(s) : \t%s'  % '; '.join( devs ) )

	if True:
		bundlePath= performBuild( appName= argObject.appName , projectDir= argObject.projectRoot
			, buildOutputDir= argObject.buildTestOutputDir , doClean= argObject.cleanSwitch )
		if bundlePath == None:
			_errorExit( "No bundle path returned!" )
	else:
		_infoTs( "skipped build to shortcut test!!" )
	for dev in devs:
		for lang in langs:

			if True:
				deployAppToDeviceAndSetLang( lang= lang, dev= dev, bundlePath= bundlePath )
			else:
				_infoTs( "skipped Deploying App to shortcut test!!" )

			startUITestTarget( projectDir= argObject.projectRoot
				, outputDir= argObject.buildTestOutputDir
				, lang= lang, dev= dev, appName= argObject.appName )

			devPretty= makeExpandFriendlyPath( dev )
			langPretty= makeExpandFriendlyPath( lang )
			pngTargetDir = os.path.join( screenshotsArchiveRoot, "%s_%s" % ( devPretty, langPretty ) )
			# give user a chance to keep the content of the target directory
			assertScreenshotsBackupDir ( pngTargetDir )

			pngSourceDir = "/Users/bmlam/Temp/ManyTimes/Screenshots"  # this is hardwired in swift test program
			backupScreenshots( srcRoot= pngSourceDir, tgtDir= pngTargetDir )

			_infoTs( "Done with simulator %s and lang %s" % ( dev, lang ) )
			closeSimulatorApp()

	_infoTs( "\n\n%s completed normally." % scriptBasename , True )
			
main()

