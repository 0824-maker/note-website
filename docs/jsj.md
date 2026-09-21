#计算机程序设计-课堂笔记
m是否为素数
除了1和本身以外不能被其他数所整除
如果m能被2整除为真跳出=》if(m%2==0)break
如果m能被3整除为真跳出
如果m能被i整除为真跳出
如果m能被sqrt（m）整除为真跳出
m=2; i=2;flag=1;
while(i<=sqrt(m)&&flag==1)
{if(m%i==0)flag=5;
i=i+1;}
if(flag==1)printf("%d\n",m);


#include <stdio.h>
#include <math.h>
 main()
{short i,m;
m=2; i=2;flag=1;
while(i<=sqrt(m)&&flag==1)
{if(m%i==0)flag=0;i=i+1;}
if(flag==1)printf("%d\n",m);

m=3; i=2;flag=1;
while(i<=sqrt(m)&&flag==1)
{if(m%i==0)flag=0;i=i+1;}
if(flag==1)
printf("%d\n",m);

m=100; i=2;flag=1;
while(i<=sqrt(m)&&flag==1)
{if(m%i==0)flag=0;i=i+1;}
if(flag==1)printf("%d\n",m);

}



#include <stdio.h>
#include <math.h>
 main()
{short i,m;
m=2;
While(m<=100)
{ i=2;flag=1;
while(i<=sqrt(m)&&flag==1)
{if(m%i==0)flag=0;i=i+1;}
if(flag==1)printf("%d\n",m);
m=m+1;
}
}
2	3	4	5	6	7	8	9	10...500
2	3	4	5	6	7	8	9	10
1	1	1	1	1	1	1	1	1
2			0		0		0		0
3								0
#include<math.h>
main()
{short i,a[101],j;
i=2;while(i<=100){a[i]=i;i=i+1;}
i=2;
while(i<=sqrt(100))
{
	if(a[i]!=0)//则将i的倍数全部去除
	{j=2;
	while(i*j<=100){a[i*j]=0;j=j+1;}
	}
i=i+1;
}
i=2;
while(i<=100)
{if(a[i]!=0)printf("%-5d",i);
i=i+1;}
}
#include<math.h>
main()
{short i,a[10001],j,num;
printf("请输入一个正整数:\n");
scanf("%d",&num);
i=2;
while(i<=num){a[i]=1;i=i+1;}
i=2;
while(i<=sqrt(num))
{
	if(a[i]!=0)//则将i的倍数全部去除
	{j=2;
	while(i*j<=num){a[i*j]=0;j=j+1;}
	}
i=i+1;
}
i=2;
while(i<=num)
{if(a[i]!=0)printf("%-5d",i);
i=i+1;}
}
1−1/2+1/3−1/4+⋯+1/99−1/100，
i=1;flag=1;
While(i<=100)
{//if(i%2!=0)s=s+1/i;else s=s-1/i;
s=s+flag/i;
flag=-flag;
i=i+1;
}
C中，语句比如以分号结束，而分号并不一定是语句的结束标记。c程序是由函数构成，函数是由语句组成。main函数是程序的入口，不是c的关键字。
C中四种类型常量整形、实型、字符、字符串；
三种类型的变量整形、实型、字符
短整型2个字节，16个二进制位，一共有65536种可能性
0000 0000 0000 0000=0
1111 1111 1111 1111=65535
+                1
10000 0000 0000 0000=65536  
如果全部放非负数，即无符号整形那么取值范围就是0~65535
如果想存放负数，那么就是带符号整数 ，则最高位是符号位，不参与数值计算。最高位1则将剩余位取反+1
0000 0000 0000 0000=0
0111 1111 1111 1111=32767
1111 1111 1111 1111=-1
 000 0000 0000 0001=1
1000 0000 0000 0000=-32768
 111 1111 1111 1111+1=1000 0000 0000 0000
-1+1=0
=》1111 1111 1111 1111+
   0000 0000 0000 0001
  10000 0000 0000 0000
=》-32768+32767=-1
1000 0000 0000 0000+
0111 1111 1111 1111
abcd=a*8+b*4+c*2+d*1
-5
0000 0000 0000 0101
=>1111 1111 1111 1011
           main()
{short   a;//-32768~32767
short int b;//-32768~32767
unsigned short c;//0~65535
a=32768;//0000 0000 0000 00001000 0000 0000 0000=>a
//a=1000 0000 0000 0000
b=a+1;////b=1000 0000 0000 0001
c=b;
printf("%d,%d,%d\n",a,b,c);
}
main()
{short   a;//-32768~32767
short int b;//-32768~32767
unsigned short c;//0~65535
a=65536+32768.456;
b=a-1;
c=b;
printf("%d,%d,%d\n",a,b,c);
}
