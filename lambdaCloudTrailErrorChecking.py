import boto3
import datetime
import json
import requests
import os
from shutil import copyfile

cloudtrail = boto3.client('cloudtrail')
client = boto3.client('ses')
sns = boto3.client('sns')
ec2 = boto3.resource('ec2')
s3 = boto3.client('s3')

topics = sns.list_subscriptions_by_topic(TopicArn='#SNS_TOPIC_GOES_HERE')
SLACK_INCOMING_WEB_HOOK = "#SLACK_WEB_HOOK_URL_GOES_HERE"
SLACK_INCOMING_USER = "#SLACK_BOT_USERNAME"
SLACK_INCOMING_CHANNEL = "#CHANNEL"

s3bucket = "#BUCKET"
s3filekey = '#BUCKET_INDEX'

errors = cloudtrail.lookup_events(
        StartTime=datetime.datetime.now() - datetime.timedelta(minutes=90),
        EndTime=datetime.datetime.now(),
    )

events = errors['Events']

def lambda_handler(events, context):
    print 'Starting at ' + str(datetime.datetime.now())
    file_check()
    print 'Lambda function completed.'

"""Check the S3 bucket for an existing error event log.  If it exists, download it to diff against new events.  Else make a new one"""

def file_check():
    try:
        s3.head_object(Bucket=s3bucket, Key=s3filekey)
        print "error_events.txt exists in s3.  Checking for CloudTrail for changes..."
        download('/tmp/old_error_events.txt')
        populate_errors('/tmp/new_error_events.txt')
    except:
        print "Error list doesn't exist.  Creating..."
        populate_errors('/tmp/old_error_events.txt')
        
def populate_errors(x):
    print 'Looking for error events...'
    f = open(x, 'a')
    
    for i in events:
        jsonstage = json.loads(i['CloudTrailEvent'])
        try:
            var = jsonstage['errorCode']
            print 'writing ' + jsonstage['eventID']
            f.write(jsonstage['eventID'] + '\n')
        except:
            pass
    f.close()
    if x == '/tmp/old_error_events.txt':
        upload(x)
    else:
        check_errors()

"""Pull all cloudtrail logs within the last 10 minutes and parse all data into reusable variables.  Grep for fingerprints in this data to extract all errors.  First look to see if there is a session context with a username indicating its source, if there is then continue.  Verify there is an actual errorCode and if so, continue.
In the principal id if the second index starts with "i-" then get the keyvalue tag for 'Name' to use in the notification.  If not then use 
the default.  Move on to compile the notifcation for Slack, send, and repeat for the next interation"""

def check_errors():
    old_events_seen = set() # holds lines already seen
    for line in open('/tmp/old_error_events.txt', "r"):
        old_events_seen.add(line.rstrip('\n'))
    pid = ''
    for i in events:
        jsonstage = json.loads(i['CloudTrailEvent'])
        jsonparsed1 = jsonstage['requestParameters']
        jsonparsed2 = jsonstage['userIdentity']
        principalid = jsonparsed2['principalId'].split(':')
        try:
            var = jsonstage['errorCode']
            error_username = get_user(jsonparsed2)
        except:
            print 'No errors found in EventID: ' + jsonstage['eventID']
            pass
        try:
            if len(principalid) <= 1:
                pid = jsonstage['userAgent']
            elif principalid[1].startswith("i-"):
                pid = get_tag(principalid[1])
            else:
                pid = principalid[1]
            
            if jsonstage['eventID'] not in old_events_seen:
                msg = '```' + 'Error: ' + jsonstage['errorCode'] + ' on ' + jsonstage['eventTime'] + ' by ' + str(error_username) + ' via ' + jsonstage['eventSource'] + '\n' + 'Action: ' + jsonstage['eventName'] + ' by principalId: ' + pid + '\n' + 'EventID: ' + jsonstage['eventID'] + '\n' + '\n' + 'Message:' + '\n' + jsonstage['errorMessage'] + '```'
                print msg
                slack_notify(msg)
        except:
            pass
    dedup()

  
def get_user(x):
    username = ''; dict = []
    try:
        username = x['userName']
        return username
    except:
        pass
    try:
        for i in x['sessionContext']['sessionIssuer']['userName']:
            dict.append(i)
        username = ''.join(dict)
        return username
    except:
        pass

"""Gets the KeyValue tag for an EC2 instance ID"""

def get_tag(x):
    id = ''
    instances = ec2.instances.filter(InstanceIds=[x])
    for i in instances:
        for x in i.tags:
            if x['Key'] == 'Name':
                id = x['Value']
            if id == '':
                id = i.id
    return id

"""Removes duplicate event IDs and uploads back to S3"""
#This can be probably be broken up
def dedup():
    print 'Checking for duplicates and merging...'
    old_errors_seen = set() # holds lines already seen
    for line in open('/tmp/old_error_events.txt', "r"):
        old_errors_seen.add(line)
    new_errors_seen = set() # holds lines already seen
    outfile = open('/tmp/temp.txt', "a")
    for line in open('/tmp/new_error_events.txt', "r"):
        if line not in old_errors_seen: # not a duplicate
            old_errors_seen.add(line)
    for i in old_errors_seen:
        outfile.write(i)
    outfile.close()
    copyfile('/tmp/temp.txt', '/tmp/error_events.txt')
    print 'Cleaning up...'
    os.remove('/tmp/temp.txt')
    os.remove('/tmp/old_error_events.txt')
    os.remove('/tmp/new_error_events.txt')
    upload('/tmp/error_events.txt')
        
def download(x):
    print 'Downloading error_events.txt from s3...'
    s3.download_file(s3bucket, s3filekey, x)
    
def upload(x):
    print 'Uploading error_events.txt to s3...'
    s3.upload_file(x, s3bucket, s3filekey)

def slack_notify(x):
    payload = {
        "text": x,
        "username": SLACK_INCOMING_USER,
        "channel": SLACK_INCOMING_CHANNEL
    }

    req = requests.post(SLACK_INCOMING_WEB_HOOK, json.dumps(payload), headers={'content-type': 'application/json'})