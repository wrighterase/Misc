#!/bin/bash

if [[ $# -ne 6 ]]; then echo "Usage is $0 -i INSTANCE -p PROFILE -r REGION"; exit 1; fi
while getopts "hi:p:r:" opt; do
    case $opt in
        h) ;;
        i) instance=$OPTARG ;;
		p) profile=$OPTARG ;;
		r) region=$OPTARG ;;
        :) echo "Option $OPTARG requires an argument"; exit 1 ;;
    esac
done
shift $((OPTIND-1))

get_info () {
instanceid=$(aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query 'Reservations[*].Instances[*].InstanceId' --output=text)
echo "Instance ID is $instanceid"
echo "Getting $instance status..."
while state=$(aws --profile $profile --region $region ec2 describe-instances --instance-id $instanceid --query 'Reservations[*].Instances[*].State.Name' --output=text); do
        if [[ $state == "stopped" ]]; then
        		echo -e "\t>>>$instance stopped\n"
                break
        elif [[ $state == "running" ]]; then
                echo "$instance is $state.  Stopping..."
                aws --profile $profile --region $region ec2 stop-instances --instance-id $instanceid > /dev/null
                sleep 3
                continue
        elif [[ $state == "stopping" || $state == "shutting-down" ]]; then
                sleep 3
                continue
        fi
done
echo "Getting volumes of $instance"
for i in `aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query "Reservations[*].Instances[*].BlockDeviceMappings[*].DeviceName" --output=text`; do echo -e "\t$i"; done
get_volumes
}

get_volumes () {
index=0
for mount_point in $(aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query "Reservations[*].Instances[*].BlockDeviceMappings[*].DeviceName" --output=text); do
	echo -e "\nStarting processes for volume mounted as $mount_point on $instance..."
	blockmap
done
###UNCOMMENT ONLY IF YOU WANT THE INSTANCE TO START AT THE END OF THE LOOP
start_instance
}

blockmap () {
while blockmap=$(aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query "Reservations[*].Instances[*].BlockDeviceMappings[$index].DeviceName" --output=text); do
	volumeid=$(aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query "Reservations[*].Instances[*].BlockDeviceMappings[$index].Ebs.VolumeId" --output=text)
	encryptedstatus=$(aws --profile $profile --region $region ec2 describe-volumes --volume-id $volumeid --query 'Volumes[*].Encrypted' --output=text)
	if [[ "$blockmap" == "$mount_point" ]] && [[ "$encryptedstatus" == "True" ]]; then
		echo "Volume $volumeid is already encrypted.  Skipping..."
		let index+=1
		break
	elif [[ "$blockmap" == "$mount_point" ]] && [[ "$encryptedstatus" != "True" ]]; then
		az=$(aws --profile $profile --region $region ec2 describe-instances --filters "Name=tag:Name,Values=$instance" --query 'Reservations[*].Instances[*].Placement.AvailabilityZone' --output=text)
		echo "Volume: $volumeid attached as $mount_point in AvailabilityZone: $az"
		aws --profile $profile --region $region ec2 create-tags --resource $volumeid --tags Key=Name,Value="$instance $mount_point"
		snapshot
		break
	else
		echo "Error occured matching device to block map index."
		let index+=1
		continue
	fi
done
}

snapshot () {
echo "Taking snapshot..."
snap=$(aws --profile $profile --region $region ec2 create-snapshot --volume-id $volumeid --description "$instance snapshot of $mount_point" --output=text | grep -o 'snap-[[:alnum:]]*')
echo -e "Waiting for snapshot to complete..."
while snapstatus=$(aws --profile $profile --region $region ec2 describe-snapshots --snapshot-id $snap --query 'Snapshots[*].State' --output=text); do
	if [[ $snapstatus == "pending" ]]; then
		continue
	else [[ $snapstatus == "completed" ]]
		echo -e "\t>>>Complete.\n"
		break
	fi
done
echo "Snapshot ID is $snap"

echo "Making copy..."
encrypted=$(aws --profile $profile --region $region ec2 copy-snapshot --source-snapshot-id $snap --description "$instance encrypted snapshot of $mount_point" --encrypted --source-region $region --output=text | grep -o 'snap-[[:alnum:]]*')
echo "Encrypting snapshot..."
while status=$(aws --profile $profile --region $region ec2 describe-snapshots --snapshot-id $encrypted --query 'Snapshots[*].State' --output=text); do
	if [[ $status == "pending" ]]; then
		sleep 2
		continue
	else [[ $status == "completed" ]]
		echo -e "\t>>>Complete.\n"
		break
	fi
done
echo "New snapshot ID is: $encrypted"
create_volume
}

create_volume () {
echo "Creating new volume..."
newvol=$(aws --profile $profile --region $region ec2 create-volume --snapshot-id $encrypted --availability-zone $az --volume-type gp2 --output=text | grep -o 'vol-[[:alnum:]]*')
aws --profile $profile --region $region ec2 create-tags --resource $newvol --tags Key=Name,Value="$instance $mount_point encrypted volume"
while volumestatus=$(aws --profile $profile --region $region ec2 describe-volumes --volume-id $newvol --query 'Volumes[*].State' --output=text); do
	if [[ $volumestatus == 'creating' ]]; then
		sleep 2
		continue
	else [[ $volumestatus == 'available' ]]
		echo -e "\t>>>Completed.\n"
		break
	fi
done
echo "New volume is $newvol"
assign
}

assign () {
echo "Detaching $volumeid from $instance"
aws --profile $profile --region $region ec2 detach-volume --instance-id $instanceid --volume-id $volumeid --device $mount_point > /dev/null
echo "Attaching $newvol as $mount_point to $instance"
aws --profile $profile --region $region ec2 attach-volume --instance-id $instanceid --volume-id $newvol --device $mount_point > /dev/null
}

start_instance () {
echo "Starting $instance"
aws --profile $profile --region $region ec2 start-instances --instance-id $instanceid > /dev/null
}

get_info
