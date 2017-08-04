import os
import json
import requests
import boto3
import datetime

ec2 = boto3.resource('ec2')
cloudtrail = boto3.client('cloudtrail')
client = boto3.client('ses')
sns = boto3.client('sns')

topics = sns.list_subscriptions_by_topic(TopicArn='#SNS_TOPIC_GOES_HERE')
SLACK_INCOMING_WEB_HOOK = "#SLACK_WEB_HOOK_URL_GOES_HERE"
SLACK_INCOMING_USER = "#SLACK_BOT_USERNAME"
SLACK_INCOMING_CHANNEL = "#CHANNEL"

runevents = cloudtrail.lookup_events(
        LookupAttributes=[
            {
                'AttributeKey': 'EventName',
                'AttributeValue': 'RunInstances'
            },
        ],
        StartTime=datetime.datetime.now() - datetime.timedelta(minutes=90),
        EndTime=datetime.datetime.now(),
    )
events = runevents['Events']

def lambda_handler(events, context):
    print 'Starting'
    runevents()
    print 'Lambda function completed.'

"""This will run on a weekly basis.  It will look at ALL Production EC2 instances and their attached EBS volumes to verify that they are encrypted.  If not it will notify that
an instance is not in compliance so that it can be remediated."""

def runevents():
    for i in events:
        for x in i['Resources']:
            if x['ResourceType'] == 'AWS::EC2::VPC' and x['ResourceName'] == '#PROD VPCID':
                get_id()

#Grab all Production instances
def get_id():
    for i in events:
        for x in i['Resources']:
            if x['ResourceType'] == 'AWS::EC2::Instance':
                ec2id = x['ResourceName']
                html = "<h6>For more information: <a class=\"ulink\" href=\"https://us-west-2.console.aws.amazon.com/cloudtrail/home?region=us-west-2#/events?EventId=" + i['EventId'] + "\" target=\"_blank\">View this CloudTrail event in the AWS console</a>.</h6>"
                audit(ec2id, html)

#Check each instance and their attached volumes for an encrypted attribute.  If it is not in compliance add it to the list to be sent out as a notification
def audit(x, y):
    list = []
    instance = ec2.Instance(x)
    volumes = instance.volumes.all()
    for v in volumes:
        if v.encrypted == False:
            list.append('INSTANCE: ' + x + ' HAS ' + v.attachments[0]['VolumeId'] + ' ATTACHED AS ' \
            + v.attachments[0]['Device'] + ' AND IS NOT ENCRYPTED!')
    if list != []:
        mail = '<br><br>'.join(list) + y
        slack = '```' + '\n'.join(list) + '```'
        ses_email(mail)
        slack_notify(slack)
        print list

def ses_email(x):
	subs = topics['Subscriptions']
	x = '<h6>' + x + '</h6>'
	for i in subs:
		emailaddress = (i['Endpoint'])
		response = client.send_email(
   		Source='noreply@domain.com',
   		Destination={
       		'ToAddresses': [
       		emailaddress
       		]
   		},

   		Message={
       		'Subject': {
       		'Data': 'AWS EC2 Auditing',
       		'Charset': 'UTF-8'
       		},
       		'Body': {
         	  	'Html': {
         	      	'Data': x ,
            	   	'Charset': 'UTF-8'
      	     	}
    	   	}
	   	}
	)
		print 'Notifying ' + emailaddress
	print "Completed."

def slack_notify(x):
    payload = {
        "text": x,
        "username": SLACK_INCOMING_USER,
        "channel": SLACK_INCOMING_CHANNEL
    }

    req = requests.post(SLACK_INCOMING_WEB_HOOK, json.dumps(payload), headers={'content-type': 'application/json'})
    