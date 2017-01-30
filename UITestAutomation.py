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

	One way to bring up the Simulator GUI of the targeted device is Simulator -> Hardware -> <choose dvice>. Doing so may return the error message: "device already booted" so we need to "simctl shutdown <device>" first.
	So if "simctl launch" is decoupled from the Simulator GUI, does it mean we could test devices in parallel?

"""

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

	appPath = os.path.join( buildOutputDir, appName + '.app' )
	
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


	_infoTs( "Run 'ls -l %s' to verify app has been built ok! Or fix me to show the file mod time" % appPath )

	if len( errOutput ) > 0 :
		errLines = errOutput.split( "\n" )
		_dbx( "lines in stderr: %d" % len( errLines ) )
		_infoTs( "Last lines of stderr:\n%s\n" % ( '\n'.join( errLines[ -10: ] ) ) )

		buildStderrPath = tempfile.mktemp()
		errF = open( buildStderrPath, "w" )
		_infoTs( "****************** Piping xcodebuild stderr to '%s'" % ( buildStderrPath ) )
		errF.write( errOutput )
		errF.close( )

		answer = raw_input( "Continue processing? Enter 'yes' to proceed or anything else to abort: " )
		if answer == 'yes':
			None # back to common path
		else:
			_errorExit( "Script aborted on demand" )

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

def backupScreenshots( srcRoot, tgtRoot, lang, dev ):
	"""
	"""
	tgtDir = os.path.join( tgtRoot, makeExpandFriendlyPath( dev ), lang )
	mkdir( tgtDir )

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

def deployAppToDeviceAndSetLang( lang, dev ):
	"""
	Since we do not know another way to change the language setting of the Simulator, the next best
	approach seems to be setting the language for the app, and this seems to be possible only while we
	are deploying it
	"""

def startUITestTarget( lang, dev, outputDir ):
	"""
	Sofar I only know how to call xcodebuild to build the app and test target and run the test target.
	I have seen that the language set for the app previously using "xcrun " does get persisted in the Simulator.
	It is indeed stupid to build again but until I know a more efficient way, I have to put up with
	this monkey solution.
	"""

def main():
	scriptBasename = os.path.basename( __file__ )
	argObject = parseCmdLine()

	_infoTs( "Build and test output dir will be '%s'" % argObject.buildTestOutputDir )

	screenshotsArchiveRoot = argObject.screenshotsArchiveRoot 

	# we check dir backup directory at this early stage so not too time is wasted when user does
	# want to keep the content of the target directory
	assertScreenshotsBackupRoot ( screenshotsArchiveRoot )
	_infoTs( "Screenshots will be backed up to '%s'" % screenshotsArchiveRoot )

	devs, langs = getListOfLangsAndDevicesFromFile ( './listOfLangsAndDevices.txt' )
	_infoTs( 'Will iterate over these lang(s) : \t%s' % '; '.join( langs ) )
	_infoTs( 'Will iterate over these dev(s) : \t%s'  % '; '.join( devs ) )

	performBuild( appName= argObject.appName , projectDir= argObject.projectRoot
		, buildOutputDir= argObject.buildTestOutputDir , doClean= argObject.cleanSwitch )

	for dev in devs:
		for lang in langs:

			deployAppToDeviceAndSetLang( lang= lang, dev= dev )
			startUITestTarget( outputDir= argObject.buildTestOutputDir, lang= lang, dev= dev )

			pngSourceDir = "/Users/bmlam/Temp/ManyTimes/Screenshots"
			backupScreenshots( srcRoot= pngSourceDir, tgtRoot= g_screenshotsBakRoot, lang= lang, dev= dev )

			_infoTs( "Done with simulator %s and lang %s" % ( dev, lang ) )

	_infoTs( "\n\n%s completed normally." % scriptBasename , True )
			
main()

